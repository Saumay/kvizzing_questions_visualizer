"""backfill-qotd-numbers: tag the group's daily QOTD sessions with their real number.

QOTD ("Question of the Day") is a group-wide rotating-host daily ritual that
started 2026-03-16. Its sequential number is almost never stated in chat, so
it cannot be read off any single message for most dates. This script instead
relies on a handful of chat-confirmed anchors and a verified fact: from
2026-03-16 through 2026-06-28, exactly one QOTD happened per calendar day,
with no skips. That lets every date in that range be derived by simple
day-offset arithmetic from the anchors, cross-checked against six
independent chat-stated numbers (2026-05-04 = 50, 2026-06-15 = 92,
2026-06-22 = 99, 2026-06-24 = 101, 2026-06-27 = 104, 2026-06-28 = 105), all
of which land exactly on the formula with zero deviation.

From 2026-06-29 onward the formula shifts by exactly one: a QOTD was
confirmed hosted by Abhishek Vats on *both* 2026-06-29 and 2026-06-30, but
the chat-stated anchors on either side (105 on 6/28, 107 on 7/1) only leave
room for one more number in between. Chat text gives no way to tell which
of the two Vats sessions was the official numbered QOTD and which was an
uncounted extra (the group has precedent for this: on 2026-03-24 Vats
explicitly called his second set a "back up set" distinct from Sid K's
official one). Rather than guess, neither 6/29 nor 6/30 is tagged here;
QOTD #106 is left unassigned.

Several dates are deliberately excluded from this backfill:
  - 2026-03-17 to 2026-03-20: no QOTD host is named in chat at all. The
    numbers (2-5) are implied by the day-streak math but no session can be
    identified to attach them to.
  - 8 dates (2026-05-03, 05-05, 05-07, 05-08, 05-12, 05-22, 06-04, 07-23)
    where the session tagged "Abhishek" in the dataset is actually Abhishek
    Saluja running an unrelated themed set; the real QOTD host that day
    (Abhishek Vats) has no session captured separately in the dataset.
  - 2026-06-01, 06-23, 06-26: a confirmed QOTD host (KP, Abhishek Vats, KP)
    has no corresponding session in the dataset at all.
  - 2026-06-10: Akshay ran both his own "American Kvizolution QOTD"
    sub-series and may have also covered the main QOTD that day; the two
    can't be cleanly separated from a single session record.
  - Three parallel "QOTD"-branded sub-series with their own separate
    counters are never touched here: Akshay's "American Kvizolution QOTD",
    Abhishek Saluja's "Pop culture QotD", and Shreya's "India's Struggle for
    Independence QOTD" (started 2026-07-13).
  - 2026-07-12 through 07-14, 07-19 (Gautam's unrelated WC-final set only),
    07-20, 07-22, 07-23, 07-25, 07-28: no QOTD host for that date has a
    matching session in the dataset, or the date's host/number can't be
    determined from chat at all.

This writes to session_overrides.json's per-session "theme" field (merged in
stage6_export.py's build_sessions()), not to questions.db, since QOTD number
is session-level metadata, not a question-level field.

Usage:
    python3 -m utils.backfill_qotd_numbers                 # dry run (default)
    python3 -m utils.backfill_qotd_numbers --apply          # write changes
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_OVERRIDES_PATH = V2_DIR / "pipeline" / "config" / "session_overrides.json"

# session_id -> QOTD number, derived as described above.
QOTD_NUMBERS: dict[str, int] = {
    "2026-03-16-abhishek": 1,
    "2026-03-21-abhishek": 6,
    "2026-03-22-khandoba": 7,
    "2026-03-23-abhishek": 8,
    "2026-03-24-sidhesh": 9,
    "2026-03-25-abhishek": 11,
    "2026-03-26-abhishek": 12,
    "2026-03-27-abhishek": 13,
    "2026-03-28-khandoba": 14,
    "2026-03-29-nikhil": 16,
    "2026-03-30-abhishek": 18,
    "2026-03-31-abhishek": 19,
    "2026-05-02-nikhil": 48,
    "2026-05-04-మాन$": 50,
    "2026-05-05-abhishek": 51,
    "2026-05-06-abhishek": 52,
    "2026-05-09-akshay": 55,
    "2026-05-10-pavan": 56,
    "2026-05-11-abhishek": 57,
    "2026-05-13-abhishek": 59,
    "2026-05-14-abhishek": 60,
    "2026-05-15-akshay": 61,
    "2026-05-16-yash": 62,
    "2026-05-17-khandoba": 63,
    "2026-05-18-abhishek": 64,
    "2026-05-19-abhishek": 65,
    "2026-05-20-abhishek": 66,
    "2026-05-21-abhishek": 67,
    "2026-05-23-abhishek": 69,
    "2026-05-24-nikhil": 70,
    "2026-05-25-pavan": 71,
    "2026-05-26-abhishek": 72,
    "2026-05-27-abhishek": 73,
    "2026-05-28-abhishek": 74,
    "2026-05-29-abhishek": 75,
    "2026-05-30-akshay": 76,
    "2026-05-31-pavan": 77,
    "2026-06-02-abhishek": 79,
    "2026-06-03-abhishek": 80,
    "2026-06-05-sidhesh": 82,
    "2026-06-06-pavan": 83,
    "2026-06-07-khandoba": 84,
    "2026-06-08-abhishek": 85,
    "2026-06-09-abhishek": 86,
    "2026-06-11-abhishek": 88,
    "2026-06-12-abhishek": 89,
    "2026-06-13-abhishek": 90,
    "2026-06-14-pavan": 91,
    "2026-06-15-abhishek": 92,
    "2026-06-16-abhishek": 93,
    "2026-06-17-abhishek": 94,
    "2026-06-18-sidhesh": 95,
    "2026-06-19-shreya": 96,
    "2026-06-20-pavan": 97,
    "2026-06-21-pavan": 98,
    "2026-06-22-khandoba": 99,
    "2026-06-24-sidhesh": 101,
    "2026-06-25-abhishek": 102,
    "2026-06-27-pavan": 104,
    "2026-06-28-nikhil": 105,
    "2026-07-01-shreya": 107,
    "2026-07-02-khandoba": 108,
    "2026-07-03-lzafeer": 109,
    "2026-07-04-pavan": 110,
    "2026-07-05-abhishek": 111,
    "2026-07-06-abhishek": 112,
    "2026-07-07-abhishek": 113,
    "2026-07-08-dr": 114,
    "2026-07-09-shreya": 115,
    "2026-07-10-abhishek": 116,
    "2026-07-11-abhishek": 117,
}


def run(overrides_path: Path, apply: bool) -> None:
    overrides: dict[str, dict] = {}
    if overrides_path.exists():
        overrides = json.loads(overrides_path.read_text(encoding="utf-8"))

    to_write: list[tuple[str, str]] = []
    skipped_already_set = 0
    for session_id, number in QOTD_NUMBERS.items():
        theme = f"QOTD #{number}"
        existing = overrides.get(session_id, {}).get("theme")
        if existing == theme:
            skipped_already_set += 1
            continue
        to_write.append((session_id, theme))

    print(f"QOTD sessions to tag: {len(QOTD_NUMBERS)}")
    print(f"Already set to the correct theme: {skipped_already_set}")
    print(f"To write: {len(to_write)}")

    if apply:
        for session_id, theme in to_write:
            overrides.setdefault(session_id, {})["theme"] = theme
        overrides_path.write_text(
            json.dumps(overrides, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Applied: {len(to_write)} session themes written to {overrides_path}.")
    else:
        for session_id, theme in to_write:
            print(f"  {session_id} -> {theme}")
        print("Dry run: re-run with --apply to write changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    parser.add_argument(
        "--overrides", type=Path, default=DEFAULT_OVERRIDES_PATH, help="Path to session_overrides.json"
    )
    args = parser.parse_args()
    run(overrides_path=args.overrides, apply=args.apply)
