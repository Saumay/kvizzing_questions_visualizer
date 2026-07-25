"""
Video recording links for hosted quiz sessions, pulled from a shared OneDrive
folder (tracked by the group in a Google Sheet). Linked directly rather than
re-hosted on R2 — these are large video files and the OneDrive share links
are already accessible.

Two kinds of entries:
- ATTACH: recording for a deck/round that already exists in the manifest
  (build_decks_manifest.py). Keyed by (series_id, round) or standalone id.
- NEW: sessions that have a recording but no slides/deck at all.
"""

from __future__ import annotations

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _recording_file(url: str, label: str = "Recording") -> dict:
    return {
        "label": label,
        "rel_path": None,
        "format": "recording",
        "r2_key": None,
        "url": url,
        "size_bytes": 0,
    }


def load_urls_by_row_index(csv_path: Path) -> dict[int, str]:
    """Row index -> URL, for splicing into the mapping below without
    hand-copying 40 OneDrive redeem URLs."""
    rows = list(csv.reader(csv_path.open()))
    return {i: r[1] for i, r in enumerate(rows) if len(r) >= 2 and r[1]}


# Attach a recording to an existing deck/round.
# target: ("series", series_id, round_number) or ("standalone", id, None)
ATTACH = [
    (("series", "gauntlet", 3), 33),
    (("series", "gauntlet", 4), 34),
    (("series", "gauntlet", 6), 35),
    (("series", "gauntlet", 7), 36),
    (("series", "gauntlet", 8), 37),
    (("series", "gauntlet", 9), 38),
    (("series", "gauntlet", 10), 39),
    (("series", "gauntlet", 11), 40),
    (("series", "gauntlet", 12), 41),
    (("series", "gauntlet", 13), 42),
    (("series", "gauntlet", 14), 43),   # also: host LZA -> "Lzafeer"
    (("series", "gauntlet", 15), 44),
    (("series", "gauntlet", 16), 45),
    (("series", "gauntlet", 17), 46),
    (("series", "gauntlet", 18), 47),
    (("series", "gauntlet", 19), 48),
    (("series", "mtv-tournament", 1), 28),
    (("series", "mtv-tournament", 2), 29),
    (("series", "mtv-tournament", 3), 30),
    (("series", "movie-quiz-bijal", 1), 4),   # one recording covers both sets
    (("series", "movie-quiz-bijal", 2), 4),
    (("standalone", "buzzer-bhide", None), 5),
    (("standalone", "may-the-4th", None), 6),
    (("standalone", "history-smit", None), 9),
    (("standalone", "tapish-sports", None), 10),
    (("standalone", "rewind-2025", None), 1),
]

# Old School Quiz has two recording parts but a single PDF deck.
OLD_SCHOOL_PARTS = [(24, "Recording (Part 1)"), (25, "Recording (Part 2)")]

# Gauntlet rounds with a recording but no deck file at all.
NEW_GAUNTLET_ROUNDS = [
    {"round": 20, "title": "Gauntlet 20", "host": "Chinmay", "date": "2026-07-11",
     "date_approx": True, "row": 49},
    {"round": 21, "title": "It is Vat itteezz", "host": None, "date": "2026-07-19",
     "date_approx": True, "row": 50},
]

NEW_SERIES = [
    {
        "id": "breaking-bad-quiz", "title": "Breaking Bad Quiz", "description": None,
        "rounds": [
            {"round": 1, "title": "The Rule", "host": None, "date": "2026-05-25",
             "date_approx": True, "row": 20},
            {"round": 2, "title": "Semi-final 2", "host": None, "date": "2026-06-01",
             "date_approx": True, "row": 21},
        ],
    },
    {
        "id": "fireside-chats", "title": "Fireside Chats",
        "description": "Casual long-form conversations.",
        "rounds": [
            {"round": 1, "title": "Art", "host": "KP", "date": "2026-02-08",
             "date_approx": True, "row": 14},
            {"round": 2, "title": "Literature", "host": "Shvetal", "date": "2026-05-23",
             "date_approx": True, "row": 15},
            {"round": 3, "title": "Fireside Chat", "host": "Shreya", "date": "2026-06-21",
             "date_approx": True, "row": 16},
            {"round": 4, "title": "Religion and Atheism", "host": None, "date": "2026-06-28",
             "date_approx": True, "row": 17},
        ],
    },
]

NEW_STANDALONE = [
    {"id": "naman-avval-number", "title": "Avval Number", "host": "Naman",
     "date": "2026-01-04", "date_approx": True, "row": 2},
    {"id": "popcorn-buzzing-aditi", "title": "Popcorn Buzzing with Aditi", "host": "Aditi",
     "date": "2026-01-24", "date_approx": True, "row": 3},
    {"id": "tension-gourav", "title": "Tension", "host": "Gourav",
     "date": "2026-05-09", "date_approx": True, "row": 7},
    {"id": "buzzy-mushkil-hai", "title": "Buzzy Mushkil Hai", "host": "Bijal Bhatt",
     "date": "2026-05-16", "date_approx": True, "row": 8},
    {"id": "qotd-100", "title": "QOTD 100", "host": None,
     "date": "2026-06-23", "date_approx": True, "row": 11},
]
