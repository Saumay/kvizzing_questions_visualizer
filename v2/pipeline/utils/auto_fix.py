"""Programmatic auto-fix for extraction_output entries.

Normalises LLM output to schema/consistency rules without re-invoking the LLM.
Used by:
  - pipeline.py reimport (post-LLM cleanup)
  - utils.extract_loop._run_stages_for_dates (AI-as-LLM bulk path)

Fixes applied (each returns +1 to the counter):
  - INVALID_TOPIC: alias-remap topic strings
  - FORMAT_TAG: drop format tags from `tags` (they belong elsewhere)
  - TAG_VARIANT: collapse 'badly explained plots' → 'badly explained'
  - ARTIFACT: strip ↵ and edit markers from text fields
  - ORPHAN_SESSION_VAR: clear session_* fields when not is_session_question
  - COLLAB_MISMATCH: set answer_is_collaborative=true when answer_parts has multiple solvers
  - CONFIDENCE_PAIR: keep extraction_confidence and answer_confirmed in sync
  - SOLVER_MISMATCH / TIMESTAMP_MISMATCH: anchor solver/timestamp to first
    is_correct=true discussion entry
  - WRONG_CONFIRMER: only the asker may confirm
  - MEDIA_MARKER: strip media markers from confirmation_text
  - has_media on wrong roles: only hint / answer_reveal / elaboration may have media
  - CONFIRM_NO_ROLE: if answer_confirmed but no confirmation in discussion,
    promote a chat-by-asker entry; else downgrade
  - CONFIRM_IMPLICIT: if confirmation_text doesn't match explicit-affirm regex,
    downgrade answer_confirmed=false + medium confidence

Source-of-truth: this implementation matches the inline auto-fix in
pipeline.py:_run_reimport. Kept in sync via shared use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from utils.config import load_topic_aliases
from utils.audit_extraction import _is_explicit_confirm

# Format tags belong on session_quiz_type / question structure, not on `tags`.
_FORMAT_TAGS = {
    "identify", "anagram", "wordplay", "connect", "clickbait",
    "real life", "naming", "weird", "pun", "battle",
    "fill in the blank", "multi-part", "factual",
}

_MEDIA_MARKERS = {
    "image omitted", "gif omitted", "video omitted",
    "audio omitted", "document omitted",
}


def apply_auto_fixes(data: list[dict], config_dir: Optional[Path] = None) -> int:
    """Apply all auto-fixes in place. Returns total count of individual fixes."""
    if config_dir is None:
        config_dir = Path(__file__).resolve().parent.parent / "config"
    topic_aliases = load_topic_aliases(config_dir)

    fixes = 0
    for q in data:
        disc = q.get("discussion", [])

        # INVALID_TOPIC: alias remap
        if "topics" in q and isinstance(q["topics"], list):
            new_topics = [topic_aliases.get(t.lower(), t) for t in q["topics"]]
            if new_topics != q["topics"]:
                q["topics"] = new_topics
                fixes += 1

        # FORMAT_TAG
        tags = q.get("tags") or []
        clean_tags = [t for t in tags if t.lower() not in _FORMAT_TAGS]
        if len(clean_tags) != len(tags):
            q["tags"] = clean_tags
            fixes += 1

        # TAG_VARIANT
        if q.get("tags"):
            new_tags = ["badly explained" if t.lower() == "badly explained plots" else t for t in q["tags"]]
            if new_tags != q["tags"]:
                q["tags"] = new_tags
                fixes += 1

        # ARTIFACT — strip ↵ and edit markers
        for field in ("question_text", "answer_text", "confirmation_text"):
            val = q.get(field) or ""
            if val:
                cleaned = val.replace(" ↵ ", " ").replace("↵", "").replace("<This message was edited>", "").strip()
                if cleaned != val:
                    q[field] = cleaned if cleaned else None
                    fixes += 1
        for e in disc:
            val = e.get("text") or ""
            if val:
                cleaned = val.replace(" ↵ ", " ").replace("↵", "").replace("<This message was edited>", "").strip()
                if cleaned != val:
                    e["text"] = cleaned
                    fixes += 1

        # ORPHAN_SESSION_VAR
        if not q.get("is_session_question"):
            for sf in ("session_quizmaster", "session_theme", "session_quiz_type",
                       "session_connect_answer", "session_question_number", "session_announcement"):
                if q.get(sf):
                    q[sf] = None
                    fixes += 1

        # COLLAB_MISMATCH
        parts = q.get("answer_parts") or []
        if parts and not q.get("answer_is_collaborative"):
            solvers = {p["solver"] for p in parts if p.get("solver")}
            if len(solvers) > 1:
                q["answer_is_collaborative"] = True
                fixes += 1

        # confidence/confirmed pair
        if q.get("answer_confirmed"):
            if q.get("extraction_confidence") != "high":
                q["extraction_confidence"] = "high"
                fixes += 1
        else:
            if q.get("extraction_confidence") == "high":
                q["extraction_confidence"] = "medium"
                fixes += 1

        # SOLVER_MISMATCH / TIMESTAMP_MISMATCH
        solver = q.get("answer_solver")
        if solver and not q.get("answer_is_collaborative") and disc:
            first_correct = next((e for e in disc if e.get("is_correct") is True), None)
            if first_correct:
                if first_correct["username"] != solver:
                    q["answer_solver"] = first_correct["username"]
                    fixes += 1
                if first_correct.get("timestamp") != q.get("answer_timestamp"):
                    q["answer_timestamp"] = first_correct["timestamp"]
                    fixes += 1

        # WRONG_CONFIRMER
        asker = q.get("question_asker")
        if asker:
            for e in disc:
                if e.get("role") == "confirmation" and e.get("username") != asker:
                    e["role"] = "chat"
                    e["is_correct"] = None
                    fixes += 1

        # MEDIA_MARKER in confirmation_text
        ct = q.get("confirmation_text") or ""
        if ct:
            ct_clean = ct
            for marker in _MEDIA_MARKERS:
                ct_clean = ct_clean.replace(marker, "").replace(marker.title(), "")
            ct_clean = ct_clean.strip()
            if ct_clean != ct:
                q["confirmation_text"] = ct_clean if ct_clean else None
                fixes += 1

        # has_media on wrong discussion roles
        for e in disc:
            if e.get("has_media") and e.get("role") not in ("hint", "answer_reveal", "elaboration"):
                e["has_media"] = False
                fixes += 1

        # CONFIRM_NO_ROLE
        if q.get("answer_confirmed") and not any(e.get("role") == "confirmation" for e in disc):
            conf_text = (q.get("confirmation_text") or "").strip()
            matched = False
            for e in disc:
                if (e.get("role") == "chat" and e.get("username") == asker
                        and (not conf_text or e.get("text", "").strip() == conf_text)):
                    e["role"] = "confirmation"
                    e["is_correct"] = None
                    matched = True
                    fixes += 1
                    break
            if not matched:
                q["answer_confirmed"] = False
                q["confirmation_text"] = None
                q["extraction_confidence"] = "medium"
                fixes += 1

        # CONFIRM_IMPLICIT
        if q.get("answer_confirmed") and q.get("confirmation_text"):
            if not _is_explicit_confirm(q["confirmation_text"]):
                q["answer_confirmed"] = False
                q["confirmation_text"] = None
                q["extraction_confidence"] = "medium"
                for e in disc:
                    if e.get("role") == "confirmation":
                        e["role"] = "chat"
                        e["is_correct"] = None
                fixes += 1

    return fixes
