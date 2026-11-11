"""
Convert Akshay's audited_qa export (kvizzing_archive_Sep25_Jul26 zip,
audited_qa/audited_qa/*.json) into our stage2-candidate extraction_output
format, so dates we can't re-extract (dead Gemini key) can still be filled
from an already-extracted, already-audited source — no LLM call needed.

Why timestamps are re-anchored to our own raw chat instead of trusted as-is:
cross-checking several already-extracted dates showed audited_qa's own
`timestamp` field runs a consistent ~5h59m46s behind our UTC chat timestamps
(some unexplained fixed-offset artifact in Akshay's own pipeline). That
offset is only confirmed before the 2026-03-08 US DST boundary, which falls
inside our Jan-Mar target range, so it can't be trusted blindly. Instead,
for every record we search our own parsed raw chat (ground truth) for the
real message from the same asker with matching text near the estimated time,
and use ITS real timestamp. Falls back to the offset-corrected estimate only
when no real-chat match is found.

Usage:
    python3 utils/import_audited_qa.py <audited_qa_dir> <date> [<date> ...]

Writes data/extraction_output/{date}.json for each date (skips a date if
that file already exists — never overwrites a real extraction).
"""

from __future__ import annotations

import difflib
import json
import re
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent.parent
V2_DIR = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

from utils.config import load_config, load_aliases
from stages.stage1_parse import run as stage1_parse

NAIVE_OFFSET = timedelta(hours=5, minutes=59, seconds=46)
EXTRACTION_OUTPUT_DIR = V2_DIR / "data" / "extraction_output"


_GENERIC_VISUAL_RE = re.compile(
    r"^\s*\d*\.?\s*\[visual[\s-]", re.IGNORECASE
)


def _is_generic_visual_placeholder(text: str) -> bool:
    """True for audited_qa's own content-free stand-ins for image-only questions
    (e.g. '[Visual question] Identify the film from the supplied image.' or
    '[Visual-only question; identify the subject...]') — as opposed to real
    question text that merely has a '[See PDF-derived image]' suffix tag
    appended, which still carries real distinguishing content. Matching real
    chat by text similarity is unreliable for the former (nothing to match
    against), so we never trust a 'found' real-chat anchor for these — a
    manual spot-check caught one that silently grabbed unrelated banter."""
    return bool(_GENERIC_VISUAL_RE.match(text or ""))


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"<attached:[^>]*>", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_raw_messages(aliases: dict) -> dict[str, list[dict]]:
    """Parse the full current raw chat once; group messages by calendar date."""
    config = load_config(PIPELINE_DIR / "config")
    config = dict(config)
    chat_path = V2_DIR / config["chat_file"]
    lines = chat_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    messages = stage1_parse(lines, config, aliases=aliases)
    by_date: dict[str, list[dict]] = {}
    for m in messages:
        by_date.setdefault(m["timestamp"][:10], []).append(m)
    for day_msgs in by_date.values():
        day_msgs.sort(key=lambda m: m["timestamp"])
    return by_date


def _clean_username(name: str) -> str:
    name = (name or "").lstrip("~").strip()
    return name.lstrip("   \t").strip()


def resolve_username(raw_name: str | None, aliases: dict, known_usernames: set[str]) -> str | None:
    """Clean + alias-map a name, then fall back to a unique prefix match against
    our real chat's usernames (handles e.g. audited_qa's 'Dr.Namrata' vs our
    'Dr.Namrata Srinivasan') before giving up and returning the cleaned name as-is."""
    if not raw_name:
        return raw_name
    name = _clean_username(raw_name)
    if name in aliases:
        return aliases[name]
    if name in known_usernames:
        return name
    lname = name.lower()
    candidates = [u for u in known_usernames if u.lower().startswith(lname) or lname.startswith(u.lower())]
    if len(candidates) == 1:
        return candidates[0]
    return name


def _candidates_near(by_date: dict, date_str: str, anchor: datetime, window: timedelta) -> list[dict]:
    """Messages on date_str (plus neighbouring days, for windows that cross midnight)."""
    out = []
    for d in (_shift_date(date_str, -1), date_str, _shift_date(date_str, 1)):
        for m in by_date.get(d, []):
            ts = datetime.fromisoformat(m["timestamp"].rstrip("Z")).replace(tzinfo=UTC)
            if abs(ts - anchor) <= window:
                out.append(m)
    return out


def _shift_date(date_str: str, days: int) -> str:
    d = datetime.fromisoformat(date_str) + timedelta(days=days)
    return d.strftime("%Y-%m-%d")


def find_real_timestamp(
    by_date: dict, date_str: str, username: str, text: str, anchor: datetime, used: set
) -> tuple[str | None, float]:
    """Best-matching, not-yet-used real message from `username` near `anchor`.
    `used` holds (username, timestamp) pairs already claimed by an earlier
    record in this same date+asker run — needed because a rapid-fire burst of
    near-identical questions (e.g. 20 same-text visual-round posts) would
    otherwise all greedily match the single best-scoring real message.
    Returns (iso_ts or None, match_ratio); marks the chosen message used."""
    target = _norm(text)[:200]
    best_ts, best_ratio = None, 0.0
    for window_hours in (1.5, 6, 24):
        cands = [
            m for m in _candidates_near(by_date, date_str, anchor, timedelta(hours=window_hours))
            if m["username"] == username and (username, m["timestamp"]) not in used
        ]
        if not cands:
            continue
        for m in cands:
            ratio = difflib.SequenceMatcher(None, target, _norm(m["text"])[:200]).ratio()
            if ratio > best_ratio:
                best_ratio, best_ts = ratio, m["timestamp"]
        if best_ratio >= 0.5:
            break
    if best_ts is not None and best_ratio >= 0.35:
        used.add((username, best_ts))
        return best_ts, best_ratio
    return None, best_ratio


def find_answer_message(by_date: dict, date_str: str, solver: str, after_ts: str, answer_text: str) -> dict | None:
    """First real message from `solver` after `after_ts`, within 2h, best matching answer_text."""
    after = datetime.fromisoformat(after_ts.rstrip("Z")).replace(tzinfo=UTC)
    target = _norm(answer_text)[:200]
    cands = [
        m for m in _candidates_near(by_date, date_str, after + timedelta(hours=1), timedelta(hours=1, minutes=5))
        if m["username"] == solver
        and datetime.fromisoformat(m["timestamp"].rstrip("Z")).replace(tzinfo=UTC) >= after
    ]
    if not cands:
        return None
    cands.sort(key=lambda m: (
        -difflib.SequenceMatcher(None, target, _norm(m["text"])[:200]).ratio(),
        m["timestamp"],
    ))
    return cands[0]


def _confidence(status: str | None, conf: float | None) -> str:
    conf = conf or 0.0
    if status == "resolved" and conf >= 0.8:
        return "high"
    if status in ("resolved", "partial") and conf >= 0.5:
        return "medium"
    return "low"


def convert_record(rec: dict, by_date: dict, aliases: dict, known_usernames: set[str], used: set) -> dict | None:
    date_str = rec.get("date")
    question = (rec.get("question") or "").strip()
    if not date_str or not question:
        return None

    asker = resolve_username(rec.get("asker_username"), aliases, known_usernames)
    solver = resolve_username(rec.get("solver_username"), aliases, known_usernames)

    try:
        naive = datetime.fromisoformat(rec["timestamp"])
    except (KeyError, ValueError):
        return None
    anchor = (naive + NAIVE_OFFSET).replace(tzinfo=UTC)

    generic_visual = _is_generic_visual_placeholder(question)
    if generic_visual:
        real_ts, ratio = None, 0.0
    else:
        real_ts, ratio = find_real_timestamp(by_date, date_str, asker, question, anchor, used)
    question_ts = real_ts or anchor.strftime("%Y-%m-%dT%H:%M:%SZ")

    answer_text = rec.get("answer")
    answer_status = rec.get("answer_status")
    discussion = []
    answer_ts = None
    if solver and answer_text and not generic_visual:
        msg = find_answer_message(by_date, date_str, solver, question_ts, answer_text)
        if msg:
            answer_ts = msg["timestamp"]
            discussion.append({
                "timestamp": msg["timestamp"],
                "username": solver,
                "text": msg["text"],
                "role": "attempt",
                "is_correct": True,
                "has_media": msg.get("has_media", False),
            })

    media = rec.get("media") or []
    confidence = _confidence(answer_status, rec.get("answer_confidence"))
    if generic_visual:
        # Question text itself carries no verifiable content (Akshay's own
        # stand-in for an image we can't inspect) — never call this high/medium.
        confidence = "low"
    elif real_ts is None:
        # Timestamp is only offset-estimated, not ground-truth-anchored — don't
        # overstate confidence.
        confidence = "low" if confidence == "high" else confidence

    return {
        "question_timestamp": question_ts,
        "question_text": question,
        "question_asker": asker,
        "has_media": bool(media),
        "is_session_question": False,
        "session_quizmaster": None,
        "session_theme": None,
        "session_question_number": None,
        "answer_text": answer_text,
        "answer_solver": solver,
        "answer_timestamp": answer_ts,
        "answer_confirmed": answer_status == "resolved",
        "confirmation_text": None,
        "answer_is_collaborative": False,
        "answer_parts": None,
        "discussion": discussion,
        "scores_after": None,
        "extraction_confidence": confidence,
        "topic": None,
        "_audited_qa_match_ratio": round(ratio, 2),
        "_audited_qa_ts_source": "raw_chat" if real_ts else "offset_estimate",
    }


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    audited_dir = Path(sys.argv[1])
    target_dates = set(sys.argv[2:])

    aliases = load_aliases(PIPELINE_DIR / "config")
    print("Parsing raw chat…")
    by_date = load_raw_messages(aliases)
    known_usernames = {m["username"] for msgs in by_date.values() for m in msgs}

    records_by_date: dict[str, list[dict]] = {}
    for f in sorted(audited_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for rec in data:
            d = rec.get("date")
            if d in target_dates:
                records_by_date.setdefault(d, []).append(rec)

    for date_str in sorted(target_dates):
        out_file = EXTRACTION_OUTPUT_DIR / f"{date_str}.json"
        if out_file.exists():
            print(f"  [{date_str}] extraction_output already exists — skipping.")
            continue
        recs = sorted(records_by_date.get(date_str, []), key=lambda r: r.get("timestamp") or "")
        if not recs:
            print(f"  [{date_str}] no audited_qa records found — skipping.")
            continue
        used: set = set()
        candidates = [c for c in (convert_record(r, by_date, aliases, known_usernames, used) for r in recs) if c]
        candidates.sort(key=lambda c: c["question_timestamp"])
        anchored = sum(1 for c in candidates if c["_audited_qa_ts_source"] == "raw_chat")

        # Safety net: never let two questions collide on the same id (= same
        # second), whatever upstream matching produced — bump forward by 1s.
        seen_ts: set[str] = set()
        for c in candidates:
            ts = datetime.fromisoformat(c["question_timestamp"].rstrip("Z"))
            while c["question_timestamp"] in seen_ts:
                ts += timedelta(seconds=1)
                c["question_timestamp"] = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            seen_ts.add(c["question_timestamp"])

        for c in candidates:
            del c["_audited_qa_match_ratio"]
            del c["_audited_qa_ts_source"]
        EXTRACTION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  [{date_str}] {len(candidates)} questions written ({anchored} raw-chat-anchored, {len(candidates) - anchored} offset-estimated).")


if __name__ == "__main__":
    main()
