"""
Import Akshay's archivist monthly JSON into the extraction_output format,
without re-running LLM extraction.

Akshay's pipeline (github.com/akshays64/kvizzing_archivist) already
identified real Q&A pairs and confirmed answers for a given month. What it
does NOT produce: a structured discussion[] thread, stats, topics, type,
or session grouping — all of which our own stage2 LLM call normally derives
from the full day of raw chat in one shot.

This script skips that expensive day-wide LLM hunt. For each Akshay-valid
question we already know the asker, approximate timestamp, answer, and
solver — so we locate it directly in our own raw chat export, then build
discussion[] with cheap deterministic heuristics (no LLM) from the messages
around it. Topics/type are left for the normal reimport pipeline to fill
(stage4 LLM enrich is a tiny batched classification call, not a day-wide
hunt) and session grouping is left for the existing detect-sessions utility.

Output: one JSON file per date, in the exact Stage 2 candidate schema, at
data/extraction_output/<date>.json — same format `pipeline.py reimport`
already expects, so stages 3-6 run completely unmodified.

Usage:
    python3 utils/import_archivist_month.py <archivist_month.json> \
        --raw-chat PATH [--raw-chat PATH ...] [--dry-run] [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional
from zoneinfo import ZoneInfo

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from stages.stage1_parse import run as stage1_run  # noqa: E402

log = logging.getLogger("kvizzing.import_archivist")

UTC = ZoneInfo("UTC")


def _clean_username(name: Optional[str]) -> Optional[str]:
    """Akshay's asker/solver usernames sometimes carry the raw '~' WhatsApp
    prefix our own stage1 strips off; normalise so matching lines up."""
    if not name:
        return name
    return name.lstrip("~").lstrip("   \t").strip()


# ── Loading raw chat ────────────────────────────────────────────────────────

def load_messages(raw_chat_paths: list[pathlib.Path], config: dict) -> list[dict]:
    """Parse one or more raw WhatsApp export files into a single UTC-sorted
    message list, deduplicated by (timestamp, username, text)."""
    aliases_path = HERE.parent / "config" / "username_aliases.json"
    aliases = json.loads(aliases_path.read_text()).get("aliases", {}) if aliases_path.exists() else {}

    seen: set[tuple[str, str, str]] = set()
    all_msgs: list[dict] = []
    for path in raw_chat_paths:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        msgs = stage1_run(lines, config, aliases)
        for m in msgs:
            key = (m["timestamp"], m["username"], m["text"][:80])
            if key not in seen:
                seen.add(key)
                all_msgs.append(m)

    all_msgs.sort(key=lambda m: m["timestamp"])
    return all_msgs


# ── Matching an Akshay entry to a raw message ──────────────────────────────

def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _parse_local(ts: str, source_tz: ZoneInfo) -> datetime:
    """Akshay's T_Q/context timestamps are naive local time in the SAME
    source timezone as our raw chat export (confirmed by spot-checking
    several entries against v1/output_all — no timezone conversion needed,
    just attach the tz and convert to UTC like stage1 does)."""
    naive = datetime.fromisoformat(ts)
    return naive.replace(tzinfo=source_tz).astimezone(UTC)


def resolve_username(name: str, day_usernames: set[str], threshold: float = 0.7) -> str:
    """Akshay's pipeline sometimes garbles decorative WhatsApp display names
    (script-mixing, e.g. Telugu న vs Devanagari न in the same name across
    different messages). If `name` isn't one of this day's actual raw-chat
    usernames, resolve it to the closest one instead of failing to match."""
    if name in day_usernames:
        return name
    best, best_score = name, 0.0
    for candidate in day_usernames:
        score = _similar(name, candidate)
        if score > best_score:
            best_score, best = score, candidate
    return best if best_score >= threshold else name


def find_anchor(
    messages: list[dict],
    asker: str,
    text_hint: str,
    approx_utc: datetime,
    window_minutes: int = 15,
) -> Optional[int]:
    """Find the index of the raw message that best matches this Akshay
    question: same asker, within a time window of the approximate
    timestamp, highest text similarity to Akshay's cleaned question text."""
    lo = approx_utc - timedelta(minutes=window_minutes)
    hi = approx_utc + timedelta(minutes=window_minutes)
    best_idx, best_score = None, 0.0
    hint_prefix = text_hint[:120]

    for i, m in enumerate(messages):
        if m["username"] != asker:
            continue
        ts = datetime.fromisoformat(m["timestamp"].rstrip("Z")).replace(tzinfo=UTC)
        if not (lo <= ts <= hi):
            continue
        score = _similar(m["text"][:120], hint_prefix)
        # Time proximity is a tiebreaker, not the primary signal — Akshay's
        # T_Q anchor can land on any message within the question's own block.
        if score > best_score:
            best_score, best_idx = score, i

    if best_idx is not None and best_score >= 0.25:
        return best_idx

    # Fall back to pure time proximity if no text overlap at all (e.g. a
    # multi-image burst question where Akshay's cleaned text diverges a lot
    # from the raw caption-less message).
    closest_idx, closest_delta = None, None
    for i, m in enumerate(messages):
        if m["username"] != asker:
            continue
        ts = datetime.fromisoformat(m["timestamp"].rstrip("Z")).replace(tzinfo=UTC)
        if not (lo <= ts <= hi):
            continue
        delta = abs((ts - approx_utc).total_seconds())
        if closest_delta is None or delta < closest_delta:
            closest_delta, closest_idx = delta, i
    return closest_idx


# ── Building discussion[] deterministically ────────────────────────────────

_CONFIRM_WORDS = re.compile(
    r"\b(correct|right|yes+|yep|yup|bingo|spot\s*on|nailed|well\s*done|👍|✅|💯|🎯)\b",
    re.IGNORECASE,
)


def build_discussion(
    messages: list[dict],
    anchor_idx: int,
    asker: str,
    solver: Optional[str],
    answer_text: Optional[str],
    next_question_utc: Optional[datetime],
    reply_window_minutes: int,
) -> tuple[list[dict], Optional[str]]:
    """Slice messages after the anchor into a discussion thread, classifying
    each deterministically. Returns (discussion, answer_timestamp)."""
    anchor_ts = datetime.fromisoformat(messages[anchor_idx]["timestamp"].rstrip("Z")).replace(tzinfo=UTC)
    window_end = anchor_ts + timedelta(minutes=reply_window_minutes)
    if next_question_utc is not None:
        window_end = min(window_end, next_question_utc)

    # First pass: find the solver's winning message (best text match to the
    # answer, among solver's own messages in the window).
    solve_idx = None
    best_score = 0.0
    if solver:
        for i in range(anchor_idx + 1, len(messages)):
            m = messages[i]
            ts = datetime.fromisoformat(m["timestamp"].rstrip("Z")).replace(tzinfo=UTC)
            if ts > window_end:
                break
            if m["username"] != solver:
                continue
            score = _similar(m["text"], answer_text or "")
            if score > best_score:
                best_score, solve_idx = score, i
        # No decent text match — just take the solver's first message in window.
        if solve_idx is None:
            for i in range(anchor_idx + 1, len(messages)):
                m = messages[i]
                ts = datetime.fromisoformat(m["timestamp"].rstrip("Z")).replace(tzinfo=UTC)
                if ts > window_end:
                    break
                if m["username"] == solver:
                    solve_idx = i
                    break

    discussion: list[dict] = []
    answer_timestamp = None
    confirmation_text = None

    for i in range(anchor_idx + 1, len(messages)):
        m = messages[i]
        ts = datetime.fromisoformat(m["timestamp"].rstrip("Z")).replace(tzinfo=UTC)
        if ts > window_end:
            break

        entry = {
            "timestamp": m["timestamp"],
            "username": m["username"],
            "text": m["text"],
            "has_media": m.get("has_media", False),
        }

        if i == solve_idx:
            entry["role"] = "attempt"
            entry["is_correct"] = True
            answer_timestamp = m["timestamp"]
        elif m["username"] == asker:
            if solve_idx is not None and i > solve_idx:
                if confirmation_text is None and _CONFIRM_WORDS.search(m["text"]):
                    entry["role"] = "confirmation"
                    entry["is_correct"] = None
                    confirmation_text = m["text"]
                else:
                    entry["role"] = "elaboration"
                    entry["is_correct"] = None
            else:
                entry["role"] = "hint"
                entry["is_correct"] = None
        elif solve_idx is not None and i < solve_idx:
            entry["role"] = "attempt"
            entry["is_correct"] = False
        else:
            entry["role"] = "chat"
            entry["is_correct"] = None

        discussion.append(entry)

    return discussion, answer_timestamp, confirmation_text


# ── Confidence mapping ──────────────────────────────────────────────────────

def _map_confidence(score: Optional[float]) -> str:
    if score is None:
        return "low"
    if score >= 0.85:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def _map_answer_source(confirmed: bool, solver: Optional[str], confirmation_text: Optional[str]) -> Optional[str]:
    if not confirmed:
        return None
    if solver is None:
        return "asker_reveal"
    if confirmation_text:
        return "explicit_confirmation"
    return "inferred"


# ── Main conversion ──────────────────────────────────────────────────────────

def convert(
    archivist_entries: list[dict],
    messages: list[dict],
    config: dict,
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Returns (candidates_by_date, unmatched_entries).

    `messages` is the FULL sorted message pool across all loaded raw-chat
    files, not bucketed by date. Akshay's T_Q is in local source-timezone
    time, but a day's late-evening local messages convert to the *next*
    UTC calendar date (Chicago is UTC-5/-6) — bucketing by UTC date would
    silently lose exactly those messages, so matching instead relies on
    the ±window_minutes time filter in find_anchor/build_discussion to
    scope the search correctly regardless of calendar-date labels.
    """
    source_tz = ZoneInfo(config["source_timezone"])
    reply_window = config["stage2"]["heuristic_reply_window_minutes"]

    valid = [
        e for e in archivist_entries
        if (e.get("question_validity") or {}).get("is_valid")
        and (e.get("final_QA_pair") or {}).get("question")
        and (e.get("context_boundary") or {}).get("T_Q")
    ]
    valid.sort(key=lambda e: e["context_boundary"]["T_Q"])

    # Group by LOCAL date (Akshay's own date label) purely to compute
    # "next question" boundaries for discussion windowing — matching
    # itself always searches the full message pool.
    by_date: dict[str, list[dict]] = defaultdict(list)
    for e in valid:
        date = e["context_boundary"]["T_Q"][:10]
        by_date[date].append(e)

    day_usernames = {m["username"] for m in messages}
    candidates_by_date: dict[str, list[dict]] = defaultdict(list)
    unmatched: list[dict] = []

    for date, entries in by_date.items():
        for idx, e in enumerate(entries):
            qa = e["final_QA_pair"]
            meta = e["metadata"]
            asker = _clean_username(meta.get("asker_username"))
            solver = _clean_username(meta.get("solver_username"))
            if asker:
                asker = resolve_username(asker, day_usernames)
            if solver:
                solver = resolve_username(solver, day_usernames)
            answer_analysis = e.get("answer_analysis") or {}
            media_flag = e.get("media_flag") or {}

            if not asker:
                unmatched.append({**e, "_reason": "no asker_username"})
                continue

            approx_utc = _parse_local(e["context_boundary"]["T_Q"], source_tz)
            anchor_idx = find_anchor(messages, asker, qa["question"], approx_utc)
            if anchor_idx is None:
                unmatched.append({**e, "_reason": "no raw-chat match found"})
                continue

            next_q_utc = None
            if idx + 1 < len(entries):
                next_q_utc = _parse_local(entries[idx + 1]["context_boundary"]["T_Q"], source_tz)

            discussion, answer_timestamp, confirmation_text = build_discussion(
                messages, anchor_idx, asker, solver, qa.get("answer"),
                next_q_utc, reply_window,
            )

            confirmed = bool(answer_analysis.get("is_confirmed_correct"))
            candidate = {
                "question_timestamp": messages[anchor_idx]["timestamp"],
                "question_text": qa["question"],
                "question_asker": asker,
                "topics": [],
                "has_media": bool(media_flag.get("media_detected")),
                "is_session_question": False,
                "session_quizmaster": None,
                "session_theme": None,
                "session_quiz_type": None,
                "session_connect_answer": None,
                "session_announcement": None,
                "session_question_number": None,
                "answer_text": qa.get("answer"),
                "answer_solver": solver,
                "answer_timestamp": answer_timestamp,
                "answer_confirmed": confirmed,
                "confirmation_text": confirmation_text,
                "answer_source": _map_answer_source(confirmed, solver, confirmation_text),
                "answer_is_collaborative": False,
                "answer_parts": None,
                "discussion": discussion,
                "scores_after": None,
                "extraction_confidence": _map_confidence(answer_analysis.get("confidence_score")),
                "_archivist_source": e.get("_source_date"),
                "_archivist_block_index": e.get("_block_index"),
            }
            # Bucket by the candidate's OWN question_timestamp UTC date, not
            # Akshay's local T_Q date — `pipeline.py reimport` filters each
            # extraction_output/<date>.json to only the questions whose
            # (UTC-derived) q.date matches the filename, so a late-evening
            # local question that crosses into the next UTC day must be
            # written under that UTC date or reimport silently drops it.
            utc_date = candidate["question_timestamp"][:10]
            candidates_by_date[utc_date].append(candidate)

    return candidates_by_date, unmatched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archivist_json", type=pathlib.Path)
    ap.add_argument("--raw-chat", type=pathlib.Path, action="append", required=True,
                     help="Raw WhatsApp export file(s) covering this month (and ideally a few days of lookahead)")
    ap.add_argument("--out-dir", type=pathlib.Path, default=HERE.parent.parent / "data" / "extraction_output")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date", help="Only process this one date (for spot-checking)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    config = json.loads((HERE.parent / "config" / "pipeline_config.json").read_text())
    entries = json.loads(args.archivist_json.read_text())

    log.info("Loaded %d archivist entries from %s", len(entries), args.archivist_json.name)
    messages = load_messages(args.raw_chat, config)
    log.info("Parsed %d raw messages from %d file(s)", len(messages), len(args.raw_chat))

    if args.date:
        entries = [e for e in entries if ((e.get("context_boundary") or {}).get("T_Q") or "").startswith(args.date)]
        log.info("Filtered to %d entries for date %s", len(entries), args.date)

    candidates_by_date, unmatched = convert(entries, messages, config)

    total = sum(len(v) for v in candidates_by_date.values())
    log.info("Matched %d candidates across %d date(s); %d unmatched",
              total, len(candidates_by_date), len(unmatched))

    if unmatched:
        reasons = defaultdict(int)
        for u in unmatched:
            reasons[u["_reason"]] += 1
        for reason, count in reasons.items():
            log.info("  unmatched (%d): %s", count, reason)

    if args.dry_run:
        log.info("Dry run — not writing files.")
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for date, candidates in sorted(candidates_by_date.items()):
        out_path = args.out_dir / f"{date}.json"
        out_path.write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("Wrote %s (%d candidates)", out_path, len(candidates))


if __name__ == "__main__":
    main()
