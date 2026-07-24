#!/usr/bin/env python3
"""
Build v2/visualizer/static/data/decks.json from the quiz_decks/ folder.

quiz_decks/ holds raw presentation decks (PDF/PPTX/DOCX/MP4/VTT) from quiz
nights hosted by group members - a different content type from the
WhatsApp-extracted questions the rest of the pipeline handles, so this
manifest is hand-curated rather than parsed from the (inconsistent)
filenames.

Rerun after adding/removing files in quiz_decks/. `url` fields are left
null here; upload_decks_to_r2.py fills them in after uploading and rewrites
this file in place.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DECKS_DIR = REPO_ROOT / "quiz_decks"
OUT_PATH = REPO_ROOT / "v2" / "visualizer" / "static" / "data" / "decks.json"

FORMAT_BY_EXT = {
    ".pdf": "pdf",
    ".pptx": "pptx",
    ".docx": "docx",
    ".mp4": "mp4",
    ".vtt": "vtt",
}


def _file(rel_path: str, label: str | None = None) -> dict:
    """One physical file within a round: rel_path is relative to quiz_decks/."""
    ext = Path(rel_path).suffix.lower()
    return {
        "label": label,  # e.g. "Slides (PDF)" vs "Source (PPTX)" when a round has >1 format
        "rel_path": rel_path,
        "format": FORMAT_BY_EXT[ext],
        "r2_key": "decks/" + rel_path,
        "url": None,
    }


# ── Multi-round series ────────────────────────────────────────────────────

SERIES = [
    {
        "id": "gauntlet",
        "title": "The Gauntlet",
        "description": "Numbered head-to-head rounds, rotating hosts.",
        "rounds": [
            {"round": 1, "title": "Sal gets things started", "host": "Sal", "date": "2026-04-05", "date_approx": True,
             "files": [_file("Gauntlet/1. KVIZZING GAUNTLET - Sal gets things started.pdf")]},
            {"round": 2, "title": "A Wild Pavan appears", "host": "Sid K", "date": "2026-04-05", "date_approx": True,
             "files": [_file("Gauntlet/2. Quizzing Gauntlet - Sid K_A Wild Pavan appears.pdf")]},
            {"round": 3, "title": "Strike it when it's hot", "host": "Nikunj", "date": "2026-04-05", "date_approx": True,
             "files": [_file("Gauntlet/3. Gauntlet Round 3 - Nikunj_Strike it when its hot.pdf")]},
            {"round": 4, "title": "A not so redundant funda", "host": "Aditi", "date": "2026-04-05", "date_approx": True,
             "files": [_file("Gauntlet/4. Gauntlet Quiz 4 with Aditi_A not so redundant funda .pdf")]},
            {"round": 5, "title": "Jagate Raho", "host": "Zaf", "date": "2026-04-05", "date_approx": True,
             "files": [_file("Gauntlet/5. Gauntlet 5- Zaf_Jagate Raho.pdf")]},
            {"round": 6, "title": "Jis raah pe tum chal rahe ho beta", "host": "Vats", "date": "2026-04-15", "date_approx": True,
             "files": [_file("Gauntlet/6. Gauntlet- Vats_Jis raah pe tum chal rahe ho beta.pptx")]},
            {"round": 7, "title": "Add Gun to Cart", "host": "Khandoba", "date": "2026-05-03", "date_approx": True,
             "files": [
                 _file("Gauntlet/7. Gauntlet - Khandoba_Add Gun to Cart.pdf", "Slides (PDF)"),
                 _file("Gauntlet/7. Gauntlet - Khandoba_Add Gun to Cart.docx", "Source (DOCX)"),
             ]},
            {"round": 8, "title": "And through goes Nikunj", "host": "KP", "date": "2026-05-03", "date_approx": True,
             "files": [_file("Gauntlet/8. Gauntlet_VIII- KP_And through goes NIkunj.pdf")]},
            {"round": 9, "title": "GOAT Pavan - Nikunj stands firm like THE WALL", "host": "Pavan", "date": "2026-05-03", "date_approx": True,
             "files": [_file("Gauntlet/9. Gauntlet 9 - GOAT Pavan_NIkunj stands firm like THE WALL.pdf")]},
            {"round": 10, "title": "Thodi si toh lift karade", "host": "CM", "date": "2026-05-03", "date_approx": True,
             "files": [_file("Gauntlet/10. Gauntlet 10 Deck - CM_Thodi si toh lift karade.pdf")]},
            {"round": 11, "title": "Better Call Sal", "host": "Sal", "date": "2026-05-03", "date_approx": True,
             "files": [_file("Gauntlet/11. GAUNTLET XI -Better Call Sal.pdf")]},
            {"round": 12, "title": "Vats the good word", "host": "Vats", "date": "2026-05-09", "date_approx": True,
             "files": [_file("Gauntlet/12. Gauntlet XII_Vats the good word.pdf")]},
            {"round": 13, "title": "Chinmay begins a streak", "host": "Pavan", "date": "2026-05-17", "date_approx": True,
             "files": [_file("Gauntlet/13. Gauntlet 13_Pavan_ Chinmay begins a streak.pdf")]},
            {"round": 14, "title": "Gauntlet 14", "host": None, "date": "2026-05-23", "date_approx": False,
             "files": [
                 _file("Gauntlet/14. 260523_Gauntlet 14.pdf", "Slides (PDF)"),
                 _file("Gauntlet/14. 260523_Gauntlet 14.pptx", "Source (PPTX)"),
             ]},
            {"round": 15, "title": "Chinmay scores a Four", "host": "Khandoba", "date": "2026-06-05", "date_approx": True,
             "files": [_file("Gauntlet/15. Gauntlet 15 Khandoba_ Chinmay scores a Four.pdf")]},
            {"round": 16, "title": "Gauntlet 16", "host": "Bijal Bhatt", "date": "2026-06-05", "date_approx": False,
             "files": [_file("Gauntlet/16. 05062026_Gauntlet_16_BijalBhatt.pdf")]},
            {"round": 17, "title": "Seven by Nikunj", "host": "Nikunj", "date": "2026-06-19", "date_approx": True,
             "files": [_file("Gauntlet/17. Gauntlet X - Seven by Nikunj.pdf")]},
            {"round": 18, "title": "Gauntlet 18", "host": "Prajwal", "date": "2026-06-26", "date_approx": True,
             "files": [
                 _file("Gauntlet/18. Gauntlet 18 - Prajwal.pdf", "Slides (PDF)"),
                 _file("Gauntlet/18. Gauntlet 18 - Prajwal.pptx", "Source (PPTX)"),
             ]},
            {"round": 19, "title": "Humans tire but not Shreya", "host": "Gautam", "date": "2026-06-29", "date_approx": True,
             "files": [_file("Gauntlet/19. Gauntlet 19 - Gautam_Humans tire but not Shreya.pdf")]},
        ],
    },
    {
        "id": "kviz-o-krazzy",
        "title": "KVIZ-O-KRAZZY",
        "description": "Sal's tournament bracket: 4 quarters, 2 semis, a final.",
        "rounds": [
            {"round": 1, "title": "Q1", "host": "Sal", "date": "2026-04-15", "date_approx": True,
             "files": [_file("KVIZ-O-KRAZZY BY SAL/1. KVIZ-O-KRAZZY Q1.pdf")]},
            {"round": 2, "title": "Q2", "host": "Sal", "date": "2026-04-15", "date_approx": True,
             "files": [_file("KVIZ-O-KRAZZY BY SAL/2. KVIZ-O-KRAZZY Q2.pdf")]},
            {"round": 3, "title": "Q3", "host": "Sal", "date": "2026-04-15", "date_approx": True,
             "files": [_file("KVIZ-O-KRAZZY BY SAL/3. KVIZ-O-KRAZZY Q3.pdf")]},
            {"round": 4, "title": "Q4", "host": "Sal", "date": "2026-04-15", "date_approx": True,
             "files": [_file("KVIZ-O-KRAZZY BY SAL/4. KVIZ-O-KRAZZY Q4.pdf")]},
            {"round": 5, "title": "Semi-final 1", "host": "Sal", "date": "2026-04-15", "date_approx": True,
             "files": [_file("KVIZ-O-KRAZZY BY SAL/5. KVIZ-O-KRAZZY SF1.pdf")]},
            {"round": 6, "title": "Semi-final 2", "host": "Sal", "date": "2026-04-15", "date_approx": True,
             "files": [_file("KVIZ-O-KRAZZY BY SAL/6. KVIZ-O-KRAZZY SF2.pdf")]},
            {"round": 7, "title": "Finale", "host": "Sal", "date": "2026-04-15", "date_approx": True,
             "files": [_file("KVIZ-O-KRAZZY BY SAL/7. KVIZ-O-KRAZZY FINALE.pdf")]},
        ],
    },
    {
        "id": "mtv-tournament",
        "title": "MTV Quiz Tournament",
        "description": "Bijal Bhatt's quarter-final rounds.",
        "rounds": [
            {"round": 1, "title": "Quarter-final 1", "host": "Bijal Bhatt", "date": "2026-07-11", "date_approx": True,
             "files": [_file("MTV_Quiz_Tournament_BijalBhatt/MTV_Quiz_QF1.pdf")]},
            {"round": 2, "title": "Quarter-final 2", "host": "Bijal Bhatt", "date": "2026-07-12", "date_approx": True,
             "files": [_file("MTV_Quiz_Tournament_BijalBhatt/MTV_Quiz_QF2.pdf")]},
            {"round": 3, "title": "Quarter-final 3", "host": "Bijal Bhatt", "date": "2026-07-12", "date_approx": True,
             "files": [_file("MTV_Quiz_Tournament_BijalBhatt/MTV_Quiz_QF3.pdf")]},
        ],
    },
    {
        "id": "megakviz",
        "title": "Akshay's Megakviz",
        "description": None,
        "rounds": [
            {"round": 1, "title": "Semi-final 1", "host": "Akshay", "date": "2025-12-13", "date_approx": True,
             "files": [_file("Akshay_s Megakviz/MEGAKVIZ_SF_1.pdf")]},
            {"round": 2, "title": "Finale", "host": "Akshay", "date": "2026-02-15", "date_approx": True,
             "files": [_file("Akshay_s Megakviz/MEGAKVIZ_FINALE.pdf")]},
        ],
    },
    {
        "id": "movie-quiz-bijal",
        "title": "Movie Quiz - World Cinema",
        "description": None,
        "rounds": [
            {"round": 1, "title": "Set A", "host": "Bijal Bhatt", "date": "2026-04-25", "date_approx": False,
             "files": [_file("Movie_Quiz_BijalBhatt_25042026/Movie_Quiz_World_Cinema_SET_A.pdf")]},
            {"round": 2, "title": "Set B", "host": "Bijal Bhatt", "date": "2026-04-25", "date_approx": False,
             "files": [_file("Movie_Quiz_BijalBhatt_25042026/Movie_Quiz_World_Cinema_SET_B.pdf")]},
        ],
    },
    {
        "id": "buzzing-whatsapp-namrata",
        "title": "Buzzing on WhatsApp",
        "description": None,
        "rounds": [
            {"round": 1, "title": "Board 1", "host": "Namrata", "date": "2026-05-01", "date_approx": True,
             "files": [_file("Buzzing on Whatsapp- Namrata/Board 1.pdf")]},
            {"round": 2, "title": "Board 2", "host": "Namrata", "date": "2026-05-01", "date_approx": True,
             "files": [_file("Buzzing on Whatsapp- Namrata/Board 2.pdf")]},
        ],
    },
    {
        "id": "buzzing-entertainment",
        "title": "Buzzing with Entertainment",
        "description": None,
        "rounds": [
            {"round": 1, "title": "Board 1", "host": None, "date": "2025-11-08", "date_approx": True,
             "files": [_file("Buzzing with Entertainment - Board 1.pdf")]},
            {"round": 2, "title": "Board 2", "host": None, "date": "2025-11-08", "date_approx": True,
             "files": [_file("Buzzing with Entertainment - Board  2.pdf")]},
        ],
    },
]

# ── One-off decks ──────────────────────────────────────────────────────────

STANDALONE = [
    {"id": "rewind-2025", "title": "2025 Rewind: Kvest for the Best", "host": "Pavan", "date": "2026-04-04", "date_approx": True,
     "files": [
         _file("2025 Rewind-Pavan/Kvest for the Best deck.pdf", "Slides (PDF)"),
         _file("2025 Rewind-Pavan/Kvest for the Best 2025 transcript.vtt", "Transcript (VTT)"),
     ]},
    {"id": "kp-quiz-final", "title": "KP's Quiz Final", "host": "KP", "date": "2025-12-20", "date_approx": False,
     "files": [_file("251220_KP_s quiz final.pdf")]},
    {"id": "bollywood-kviz", "title": "Bollywood Kviz", "host": None, "date": "2025-12-21", "date_approx": False,
     "files": [_file("251221_BOLLYWOOD KVIZ.pdf")]},
    {"id": "buzzer-bhide", "title": "Sports Buzzing", "host": "Bhide", "date": "2026-05-03", "date_approx": False,
     "files": [_file("260503_Buzzer done quickly_Bhide/Sports Buzzing_AB.pptx")]},
    {"id": "tapish-sports", "title": "Tapish's Sports Quiz", "host": "Tapish", "date": "2026-07-05", "date_approx": False,
     "files": [_file("260705_Tapish_s Sports Quiz.pdf")]},
    {"id": "history-smit", "title": "History Quiz", "host": "Smit", "date": "2026-06-29", "date_approx": True,
     "files": [_file("History Quiz by Smit June 2026.pdf")]},
    {"id": "kvizimals", "title": "KVizimals", "host": None, "date": "2026-04-04", "date_approx": True,
     "files": [_file("KVizimals.pptx")]},
    {"id": "movie-kviz", "title": "Movie Kviz", "host": None, "date": "2025-12-07", "date_approx": True,
     "files": [_file("MOVIE KVIZ.pdf")]},
    {"id": "may-the-4th", "title": "May the 4th Quiz", "host": None, "date": "2026-05-04", "date_approx": False,
     "files": [_file("May the 4th/May_The_4th_quiz_2026.pdf")]},
    {"id": "old-school-kp", "title": "Old School Quiz", "host": "KP", "date": "2026-07-04", "date_approx": False,
     "files": [_file("Old school quiz_KP_040726.pdf")]},
    {"id": "swine-clue", "title": "Swine Clue Quiz", "host": None, "date": "2025-11-21", "date_approx": True,
     "files": [_file("Swine Clue Quiz.pdf")]},
    {"id": "visual-buzzing-bijal", "title": "Visual Buzzing Kviz", "host": "Bijal Bhatt", "date": "2026-05-16", "date_approx": False,
     "files": [_file("Visual Buzzing Kviz Bijal Bhatt_16052026/Kvizzing Visual buzzing _BijalBhatt.pdf")]},
    {"id": "yet-another-quiz", "title": "Yet Another Quiz - Part 1", "host": None, "date": "2025-11-01", "date_approx": True,
     "files": [_file("Yet Another Quiz Part 1.pdf")]},
]


def _add_sizes(files: list[dict]) -> int:
    total = 0
    for f in files:
        local = DECKS_DIR / f["rel_path"]
        size = local.stat().st_size
        f["size_bytes"] = size
        total += size
    return total


def main() -> None:
    missing: list[str] = []
    total_bytes = 0

    for s in SERIES:
        for r in s["rounds"]:
            for f in r["files"]:
                if not (DECKS_DIR / f["rel_path"]).exists():
                    missing.append(f["rel_path"])
            total_bytes += _add_sizes(r["files"])

    for d in STANDALONE:
        for f in d["files"]:
            if not (DECKS_DIR / f["rel_path"]).exists():
                missing.append(f["rel_path"])
        total_bytes += _add_sizes(d["files"])

    if missing:
        raise SystemExit("Missing files referenced in manifest:\n  " + "\n  ".join(missing))

    manifest = {
        "series": SERIES,
        "standalone": STANDALONE,
        "total_bytes": total_bytes,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(manifest, indent=2) + "\n")

    n_series_files = sum(len(r["files"]) for s in SERIES for r in s["rounds"])
    n_standalone_files = sum(len(d["files"]) for d in STANDALONE)
    print(f"Wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    print(f"  {len(SERIES)} series, {n_series_files} files")
    print(f"  {len(STANDALONE)} standalone decks, {n_standalone_files} files")
    print(f"  {total_bytes / 1024**2:.1f} MB total")


if __name__ == "__main__":
    main()
