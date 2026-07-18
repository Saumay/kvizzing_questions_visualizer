"""backfill-answer-source: populate answer.answer_source on existing DB entries.

Deterministic rules derived from signals already present in each payload —
no LLM calls. Entries extracted after the answer_source prompt upgrade keep
their LLM-assigned value (never overwritten).

Rules (first match wins):
  1. answer.text is null                      → answer_source stays null
  2. answer.confirmed is true                 → explicit_confirmation
  3. discussion contains an answer_reveal     → asker_reveal
  4. scores_after is populated                → tally_implied
  5. otherwise                                → inferred

Usage:
    python3 -m utils.backfill_answer_source           # dry run (default)
    python3 -m utils.backfill_answer_source --apply   # write changes
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import Counter
from pathlib import Path

log = logging.getLogger("kvizzing")

V2_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = V2_DIR / "data" / "questions.db"


def classify(payload: dict) -> str | None:
    """Apply the deterministic answer_source rules to one payload dict."""
    answer = payload.get("answer") or {}
    if answer.get("text") is None:
        return None
    if answer.get("confirmed"):
        return "explicit_confirmation"
    discussion = payload.get("discussion") or []
    if any(e.get("role") == "answer_reveal" for e in discussion):
        return "asker_reveal"
    if payload.get("scores_after"):
        return "tally_implied"
    return "inferred"


def run(apply: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, payload FROM questions").fetchall()

    dist: Counter = Counter()
    updates: list[tuple[str, str]] = []
    for qid, payload_json in rows:
        payload = json.loads(payload_json)
        answer = payload.get("answer") or {}

        existing = answer.get("answer_source")
        if existing:
            dist[f"kept:{existing}"] += 1
            continue

        source = classify(payload)
        dist[source or "null"] += 1
        if source is None:
            continue

        answer["answer_source"] = source
        payload["answer"] = answer
        updates.append((json.dumps(payload, ensure_ascii=False), qid))

    print(f"Total rows: {len(rows)}")
    print("Distribution:")
    for key, count in dist.most_common():
        print(f"  {key:>30}: {count}")

    if apply:
        conn.executemany("UPDATE questions SET payload = ? WHERE id = ?", updates)
        conn.commit()
        print(f"Applied: {len(updates)} rows updated.")
    else:
        print(f"Dry run: {len(updates)} rows would be updated. Re-run with --apply.")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()
    if not DB_PATH.exists():
        sys.exit(f"DB not found: {DB_PATH}")
    run(apply=args.apply)
