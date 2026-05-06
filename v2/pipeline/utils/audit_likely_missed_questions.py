"""
Scan rejected_candidates for STANDALONE candidates that are likely missed
trivia questions, complementing audit_missed_sessions.py (which only catches
clusters / sessions).

Two patterns flagged:

  1. Long-setup Q: a single rejected candidate ending with `?`, length ≥ 200
     chars (configurable). These look like substantive trivia paragraphs.

  2. Q-prefix Q: a candidate whose text starts with one of the strong
     trivia-question prefixes ("Q.", "Q1.", "Q:", "FUQ:", "Fun question",
     "Question:", "Trivia:", numbered like "7/10:", etc.).

Usage:
    python3 utils/audit_likely_missed_questions.py [--date YYYY-MM-DD]
    python3 utils/audit_likely_missed_questions.py --min-length 250

Returns exit code 1 when any candidates flagged (useful for CI / wrappers).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent.parent.parent
REJECTED_DIR = V2_DIR / "data" / "attribution_gaps" / "rejected_candidates"
DB_PATH = V2_DIR / "data" / "questions.db"


def extracted_timestamps() -> set[str]:
    """Return set of question_timestamps already extracted into the archive."""
    if not DB_PATH.exists():
        return set()
    out: set[str] = set()
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            for (payload,) in conn.execute("SELECT payload FROM questions"):
                try:
                    p = json.loads(payload)
                    ts = p.get("question", {}).get("timestamp")
                    if ts:
                        out.add(ts)
                except Exception:
                    continue
    except Exception:
        pass
    return out

# Strong start-of-message prefixes that almost always indicate a trivia Q.
PREFIX_PATTERN = re.compile(
    r"^(?:"
    r"Q\d*\s*[\.:\)]"            # Q., Q1., Q1:, Q1)
    r"|Q\s+[A-Z]"                 # "Q What ..."
    r"|Question\s*[\.:]"
    r"|Trivia\s*[\.:]"
    r"|Flash\s+Q\b"
    r"|FUQ\b"                     # follow-up question
    r"|Fun\s+(?:question|Q)\b"
    r"|Bonus\s+(?:question|Q)\b"
    r"|\d+\s*/\s*\d+\s*[\.:]"     # 7/10: or 7/10. (numbered series)
    r")",
    re.IGNORECASE,
)


def is_long_setup_q(text: str, min_len: int) -> bool:
    t = text.strip()
    return len(t) >= min_len and t.endswith("?")


def has_q_prefix(text: str) -> bool:
    return bool(PREFIX_PATTERN.match(text.strip()))


def audit_threads(threads: list[dict], min_len: int = 200,
                  skip_extracted_ts: set[str] | None = None) -> list[dict]:
    """Return list of {thread_id, date, candidate, reason}.

    If skip_extracted_ts is provided, candidates whose timestamp is in that set
    are dropped — they're already in the archive, no longer "missed".
    """
    skip_extracted_ts = skip_extracted_ts or set()
    out: list[dict] = []
    for t in threads:
        # If ANY candidate in the thread is already extracted, treat the whole
        # thread as resolved (matches export_rejected and /review UI logic).
        if any(c.get("timestamp") in skip_extracted_ts for c in t.get("candidates", [])):
            continue
        for c in t.get("candidates", []):
            text = c.get("text") or ""
            if not text.strip():
                continue
            reasons: list[str] = []
            if has_q_prefix(text):
                reasons.append("Q-prefix")
            if is_long_setup_q(text, min_len):
                reasons.append(f"long-setup ({len(text.strip())} chars)")
            if not reasons:
                continue
            out.append({
                "thread_id": t.get("id"),
                "date": t.get("date"),
                "timestamp": c.get("timestamp"),
                "username": c.get("username"),
                "preview": text.strip()[:160],
                "reasons": reasons,
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Only check this date (YYYY-MM-DD).")
    ap.add_argument("--min-length", type=int, default=200, help="Min text length for long-setup detection.")
    ap.add_argument("--rejected-dir", default=str(REJECTED_DIR))
    ap.add_argument("--include-resolved", action="store_true",
                    help="Don't filter out threads whose candidates are already extracted.")
    args = ap.parse_args()

    rejected_dir = Path(args.rejected_dir)
    if not rejected_dir.exists():
        print(f"Rejected dir not found: {rejected_dir}", file=sys.stderr)
        return 1

    skip_ts = set() if args.include_resolved else extracted_timestamps()
    if skip_ts:
        print(f"(filtering out {len(skip_ts)} already-extracted timestamps; pass --include-resolved to disable)")

    files = sorted(rejected_dir.glob(f"{args.date}.json" if args.date else "*.json"))
    if not files:
        print("No rejected files to scan.")
        return 0

    total = 0
    for f in files:
        try:
            threads = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        flags = audit_threads(threads, min_len=args.min_length, skip_extracted_ts=skip_ts)
        if not flags:
            continue
        for fl in flags:
            total += 1
            print(f"[{fl['date']}] {fl['thread_id']} {fl['username']} "
                  f"({', '.join(fl['reasons'])}) — {fl['preview']}")
    if total:
        print(f"\n{total} likely-missed standalone question(s) flagged.")
        return 1
    print("No likely-missed standalone questions found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
