"""sync-db-to-files: append DB-only questions to their extraction_output files.

Companion to audit_db_file_sync.py. For every question that exists in the DB
but not in its date's extraction_output file, converts the stored payload back
to the flat extraction format (inverse of stage3) and appends it, keeping the
file sorted by question_timestamp. Ensures a DB rebuild from files cannot
lose recall-fix era rescues.

Usage:
    python3 -m utils.sync_db_to_files           # dry run (default)
    python3 -m utils.sync_db_to_files --apply   # write changes
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from utils.audit_db_file_sync import _file_ids, DB_PATH, EXTRACTION_DIR


def _iso(ts: str | None) -> str | None:
    """Normalize payload datetime strings to the extraction format's Z-suffix ISO."""
    if not ts:
        return None
    return ts.replace("+00:00", "Z") if ts.endswith("+00:00") else (ts if ts.endswith("Z") else ts + "Z")


def payload_to_flat(p: dict) -> dict:
    """Inverse of stage3: nested payload dict → flat extraction entry."""
    q, a = p["question"], p["answer"]
    sess = p.get("session")
    discussion = []
    for e in p.get("discussion") or []:
        entry = {
            "timestamp": _iso(e["timestamp"]),
            "username": e["username"],
            "text": e["text"],
            "role": e["role"],
            "is_correct": e.get("is_correct"),
        }
        if e.get("has_media"):
            entry["has_media"] = True
        discussion.append(entry)
    return {
        "question_timestamp": _iso(q["timestamp"]),
        "question_text": q["text"],
        "question_asker": q["asker"],
        "topics": q.get("topics") or ["general"],
        "tags": q.get("tags") or [],
        "has_media": bool(q.get("has_media")),
        "is_session_question": sess is not None,
        "session_quizmaster": sess["quizmaster"] if sess else None,
        "session_theme": sess.get("theme") if sess else None,
        "session_quiz_type": sess.get("quiz_type") if sess else None,
        "session_connect_answer": sess.get("connect_answer") if sess else None,
        "session_announcement": sess.get("announcement") if sess else None,
        "session_question_number": sess["question_number"] if sess else None,
        "answer_text": a.get("text"),
        "answer_solver": a.get("solver"),
        "answer_timestamp": _iso(a.get("timestamp")),
        "answer_confirmed": bool(a.get("confirmed")),
        "confirmation_text": a.get("confirmation_text"),
        "answer_source": a.get("answer_source"),
        "answer_is_collaborative": bool(a.get("is_collaborative")),
        "answer_parts": a.get("parts"),
        "discussion": discussion,
        "scores_after": p.get("scores_after"),
        "extraction_confidence": p["extraction_confidence"],
    }


def run(apply: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, date, payload FROM questions").fetchall()
    conn.close()

    db_by_date: dict[str, dict[str, dict]] = {}
    for qid, date, payload in rows:
        db_by_date.setdefault(date, {})[qid] = json.loads(payload)

    total = 0
    for date, by_id in sorted(db_by_date.items()):
        path = EXTRACTION_DIR / f"{date}.json"
        entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        known = _file_ids(entries)
        missing = sorted(set(by_id) - known)
        if not missing:
            continue
        for qid in missing:
            entries.append(payload_to_flat(by_id[qid]))
            print(f"{date}: append {qid}")
            total += 1
        entries.sort(key=lambda e: e.get("question_timestamp", ""))
        if apply:
            path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'Appended' if apply else 'Would append'} {total} entries."
          + ("" if apply else " Re-run with --apply."))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()
    if not DB_PATH.exists():
        sys.exit(f"DB not found: {DB_PATH}")
    run(apply=args.apply)
