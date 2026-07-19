"""audit-db-file-sync: find questions present in the DB but missing from
extraction_output files (and vice versa).

Background: during recall-fix sessions some questions were upserted into the
DB (via promote-rejected or ad-hoc rescues) without appending them to the
per-date extraction_output file. A DB rebuild from files would silently lose
those rows. This audit quantifies the drift per date; it does not modify
anything.

Match key: question id (derived from question_timestamp with the same
collision-suffix logic as stage3).

Usage:
    python3 -m utils.audit_db_file_sync
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = V2_DIR / "data" / "questions.db"
EXTRACTION_DIR = V2_DIR / "data" / "extraction_output"


def _file_ids(entries: list[dict]) -> set[str]:
    """Derive DB-style ids from extraction entries (stage3 _make_id logic)."""
    counter: Counter = Counter()
    ids = set()
    for e in sorted(entries, key=lambda x: x.get("question_timestamp", "")):
        ts = e.get("question_timestamp", "")
        if not ts:
            continue
        base = f"{ts[:10]}-{ts[11:13]}{ts[14:16]}{ts[17:19]}"
        counter[base] += 1
        ids.add(base if counter[base] == 1 else f"{base}{counter[base]}")
    return ids


def run() -> int:
    conn = sqlite3.connect(DB_PATH)
    db_by_date: dict[str, set[str]] = {}
    for qid, date in conn.execute("SELECT id, date FROM questions"):
        db_by_date.setdefault(date, set()).add(qid)
    conn.close()

    file_by_date: dict[str, set[str]] = {}
    for f in sorted(EXTRACTION_DIR.glob("*.json")):
        try:
            entries = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"WARN: unparseable {f.name}")
            continue
        file_by_date[f.stem] = _file_ids(entries if isinstance(entries, list) else [])

    all_dates = sorted(set(db_by_date) | set(file_by_date))
    total_db_only = total_file_only = affected = 0
    for date in all_dates:
        db_ids = db_by_date.get(date, set())
        file_ids = file_by_date.get(date, set())
        db_only = db_ids - file_ids
        file_only = file_ids - db_ids
        if db_only or file_only:
            affected += 1
            total_db_only += len(db_only)
            total_file_only += len(file_only)
            marker = " (NO FILE)" if date not in file_by_date else ""
            print(f"{date}: {len(db_only)} db-only, {len(file_only)} file-only{marker}")
            for qid in sorted(db_only):
                print(f"    db-only:   {qid}")
            for qid in sorted(file_only):
                print(f"    file-only: {qid}")

    print(f"\n{affected}/{len(all_dates)} dates drifted; "
          f"{total_db_only} questions exist only in DB (lost on rebuild), "
          f"{total_file_only} only in files (lost/renamed in DB).")
    return 1 if total_db_only else 0


if __name__ == "__main__":
    if not DB_PATH.exists():
        sys.exit(f"DB not found: {DB_PATH}")
    sys.exit(run())
