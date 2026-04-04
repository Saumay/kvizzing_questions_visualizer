"""
Backfill missing discussion entries for extracted questions.

For each extracted question, scans the original chat messages between the
question timestamp and the next question and adds any messages not already
captured in the discussion array.

Simple classification:
  - Before answer confirmed: non-asker → attempt, asker → hint/confirmation
  - After answer confirmed: everything → chat
  - The LLM classify-discussion command can refine roles later
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

log = logging.getLogger("kvizzing")

_MAX_DISCUSSION_WINDOW_S = 1800  # 30 min for last question of the day

_CONFIRM_WORDS = frozenset([
    "correct", "yes!", "right", "ding", "bingo", "got it", "well done",
    "yep", "yess", "exactly", "spot on", "nailed it", "that's it",
    "absolutely", "perfect", "bang on", "bulls eye", "✅", "💯",
])

# Patterns that confirm when the asker is replying right after an attempt
_CONFIRM_RE = re.compile(
    r"^(?:yes|yeah|yea|yep|yess+|yup|correct|right|exactly|absolutely|perfect|bingo|"
    r"that'?s (?:it|right|correct)|spot on|nailed it|bang on|well done|got it|ding)"
    r"[\s!.,🎉👏✅💯😄😊🙌]*",
    re.IGNORECASE,
)

_REACTION_RE = re.compile(
    r"^[\s]*("
    r"😂|🤣|😅|😆|🔥|👏|💪|👍|❤️|🙌|😮|😲|🤯|🫡|🤦|💀|"
    r"haha+|lol|lmao|rofl|omg|nice|wow|damn|whoa|"
    r"oh man|oh no|oof|ooh|oops|yikes|hehe|hihi"
    r")[\s!.😂🤣😅]*$",
    re.IGNORECASE,
)


def _is_confirmation(text: str) -> bool:
    text_lower = text.lower().strip()
    for w in _CONFIRM_WORDS:
        if w in text_lower:
            return True
    # Also check if the message starts with a confirmation word/phrase
    if _CONFIRM_RE.match(text_lower):
        return True
    return False


def _is_reaction_only(text: str) -> bool:
    return bool(_REACTION_RE.match(text.strip()))


def _find_answer_timestamp(discussion: list[dict]) -> datetime | None:
    """Find when the answer was resolved — confirmation, answer_reveal, or correct attempt."""
    for d in discussion:
        if d.get("role") in ("confirmation", "answer_reveal"):
            ts = d.get("timestamp", "")
            if ts:
                try:
                    return datetime.fromisoformat(ts.rstrip("Z"))
                except Exception:
                    pass
    for d in discussion:
        if d.get("role") == "attempt" and d.get("is_correct") is True:
            ts = d.get("timestamp", "")
            if ts:
                try:
                    return datetime.fromisoformat(ts.rstrip("Z"))
                except Exception:
                    pass
    return None


def backfill(
    questions_by_date: dict[str, list[dict]],
    messages_by_date: dict[str, list[dict]],
    dry_run: bool = False,
) -> dict[str, int]:
    """
    For each date's extracted questions, find chat messages that belong to each
    question's discussion but weren't captured by the LLM.

    Uses the next question's timestamp as the window end.
    For the last question of the day, uses a 30-min window.
    """
    results: dict[str, int] = {}

    for date_str in sorted(questions_by_date.keys()):
        qs = questions_by_date[date_str]
        msgs = messages_by_date.get(date_str, [])
        if not qs or not msgs:
            continue

        qs_sorted = sorted(qs, key=lambda q: q.get("question_timestamp", ""))
        added_count = 0

        for qi, q in enumerate(qs_sorted):
            q_ts_str = q.get("question_timestamp", "")
            if not q_ts_str:
                continue

            try:
                q_dt = datetime.fromisoformat(q_ts_str.rstrip("Z"))
            except Exception:
                continue

            q_asker = q.get("question_asker", "")

            # Window end
            if qi + 1 < len(qs_sorted):
                next_ts = qs_sorted[qi + 1].get("question_timestamp", "")
                try:
                    window_end = datetime.fromisoformat(next_ts.rstrip("Z"))
                except Exception:
                    window_end = q_dt + timedelta(seconds=_MAX_DISCUSSION_WINDOW_S)
            else:
                window_end = q_dt + timedelta(seconds=_MAX_DISCUSSION_WINDOW_S)

            discussion = q.get("discussion") or []
            existing_ts = {d.get("timestamp", "") for d in discussion}
            answer_dt = _find_answer_timestamp(discussion)

            new_entries = []
            for msg in msgs:
                msg_ts_str = msg["timestamp"]
                try:
                    msg_dt = datetime.fromisoformat(msg_ts_str.rstrip("Z"))
                except Exception:
                    continue

                if msg_dt <= q_dt or msg_dt >= window_end:
                    continue
                if msg_ts_str in existing_ts or msg_ts_str == q_ts_str:
                    continue

                text = msg.get("text", "").strip()
                if not text or msg.get("username", "") == "system":
                    continue
                if _is_reaction_only(text):
                    continue

                username = msg["username"]
                is_after_answer = answer_dt is not None and msg_dt > answer_dt

                # Simple classification
                if username == q_asker:
                    if _is_confirmation(text):
                        role = "confirmation"
                        if answer_dt is None:
                            answer_dt = msg_dt
                    elif is_after_answer:
                        role = "chat"
                    else:
                        role = "hint"
                else:
                    role = "chat" if is_after_answer else "attempt"

                new_entries.append({
                    "timestamp": msg_ts_str,
                    "username": username,
                    "text": text,
                    "role": role,
                    "is_correct": None,
                    "has_media": bool(msg.get("has_media")),
                })

            if new_entries:
                if dry_run:
                    log.info(
                        "  [%s] Q [%s] %s: would add %d discussion entries",
                        date_str, q_ts_str[11:19], q_asker, len(new_entries),
                    )
                    for e in new_entries[:5]:
                        log.info("    + [%s] %s [%s]: %s", e["timestamp"][11:19], e["username"], e["role"], e["text"][:80])
                    if len(new_entries) > 5:
                        log.info("    ... and %d more", len(new_entries) - 5)
                else:
                    discussion.extend(new_entries)
                    discussion.sort(key=lambda d: d.get("timestamp", ""))
                    q["discussion"] = discussion

                added_count += len(new_entries)

        if added_count > 0:
            results[date_str] = added_count

    return results


def reclassify(
    questions_by_date: dict[str, list[dict]],
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Re-classify roles of existing discussion entries.
    Only fixes obvious misclassifications — keeps it simple.
    """
    results: dict[str, int] = {}

    for date_str in sorted(questions_by_date.keys()):
        qs = questions_by_date[date_str]
        if not qs:
            continue

        reclass_count = 0
        qs_sorted = sorted(qs, key=lambda q: q.get("question_timestamp", ""))

        for q in qs_sorted:
            discussion = q.get("discussion") or []
            if not discussion:
                continue

            q_asker = q.get("question_asker", "")
            answer_dt = _find_answer_timestamp(discussion)

            for d in discussion:
                # Skip LLM-extracted entries
                if d.get("is_correct") is not None:
                    continue

                text = d.get("text", "").strip()
                username = d.get("username", "")
                old_role = d.get("role", "")
                ts = d.get("timestamp", "")

                if not text or not ts:
                    continue

                try:
                    msg_dt = datetime.fromisoformat(ts.rstrip("Z"))
                except Exception:
                    continue

                is_after_answer = answer_dt is not None and msg_dt > answer_dt

                # Determine correct role
                if username == q_asker:
                    if _is_confirmation(text):
                        new_role = "confirmation"
                    elif is_after_answer:
                        new_role = "chat"
                    else:
                        new_role = "hint"
                else:
                    new_role = "chat" if is_after_answer else "attempt"

                if new_role != old_role:
                    if not dry_run:
                        d["role"] = new_role
                    reclass_count += 1

        if reclass_count > 0:
            results[date_str] = reclass_count

    return results
