"""backfill-media-unavailable: mark confirmed-permanent media gaps ("Phase B").

Some chat-mined live-quiz sessions have has_media=True questions whose media
was never captured in any available WhatsApp export/backup — confirmed via
exhaustive search (see v2/BACKLOG.md "Media backlog": raw media coverage runs
2025-09-23 through 2026-04-01, with nothing found for 2026-04-02 onward until
2026-09-16). The dates below fall inside that documented gap and were
specifically identified as genuine, non-duplicate live-quiz sessions (not
chat-fabricated placeholders) whose source images are permanently missing.

This sets media_unavailable=True on exactly those rows, so the frontend can
show a clean "image unavailable" state instead of implying extraction is
still pending. It does NOT touch the broader has_media=True/media=null
population elsewhere in the dataset — that remains the normal
"not yet extracted" state.

Usage:
    python3 -m utils.backfill_media_unavailable                 # dry run (default)
    python3 -m utils.backfill_media_unavailable --apply          # write changes
    python3 -m utils.backfill_media_unavailable --db PATH --apply  # explicit DB path
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = V2_DIR / "data" / "questions.db"

# Dates confirmed (2026-11-11 investigation) to fall entirely inside the
# documented 2026-04-02..2026-09-16 raw-media gap, where chat-mined live-quiz
# sessions collide on-date with an unrelated deck-extracted session.
CONFIRMED_GAP_DATES = [
    "2026-05-03",
    "2026-05-16",
    "2026-05-17",
    "2026-06-05",
    "2026-06-19",
    "2026-06-26",
    "2026-06-29",
    "2026-07-04",
    "2026-07-05",
    "2026-07-11",
    "2026-07-12",
    "2026-07-19",
]


def run(db_path: Path, apply: bool) -> None:
    conn = sqlite3.connect(db_path)
    placeholders = ",".join("?" for _ in CONFIRMED_GAP_DATES)
    rows = conn.execute(
        f"SELECT id, payload FROM questions "
        f"WHERE date IN ({placeholders}) AND has_media = 1",
        CONFIRMED_GAP_DATES,
    ).fetchall()

    updates: list[tuple[str, str]] = []
    skipped_has_media_resolved = 0
    skipped_already_set = 0
    for qid, payload_json in rows:
        payload = json.loads(payload_json)
        question = payload.get("question") or {}

        if question.get("media") is not None:
            # Media was matched after all (e.g. a later pipeline run) — leave it alone.
            skipped_has_media_resolved += 1
            continue
        if question.get("media_unavailable"):
            skipped_already_set += 1
            continue

        question["media_unavailable"] = True
        payload["question"] = question
        updates.append((json.dumps(payload, ensure_ascii=False), qid))

    print(f"Dates checked: {len(CONFIRMED_GAP_DATES)}")
    print(f"has_media=1 rows in those dates: {len(rows)}")
    print(f"Already had media_unavailable=True: {skipped_already_set}")
    print(f"Skipped (media now present): {skipped_has_media_resolved}")
    print(f"To mark media_unavailable=True: {len(updates)}")

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
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to questions.db")
    args = parser.parse_args()
    if not args.db.exists():
        sys.exit(f"DB not found: {args.db}")
    run(db_path=args.db, apply=args.apply)
