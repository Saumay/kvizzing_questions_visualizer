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
import sys
from pathlib import Path

REJECTED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "attribution_gaps" / "rejected_candidates"

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


def audit_threads(threads: list[dict], min_len: int = 200) -> list[dict]:
    """Return list of {thread_id, date, candidate, reason}."""
    out: list[dict] = []
    for t in threads:
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
    args = ap.parse_args()

    rejected_dir = Path(args.rejected_dir)
    if not rejected_dir.exists():
        print(f"Rejected dir not found: {rejected_dir}", file=sys.stderr)
        return 1

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
        flags = audit_threads(threads, min_len=args.min_length)
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
