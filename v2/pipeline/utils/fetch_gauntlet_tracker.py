"""
Fetch the Gauntlet Tracker Google Sheet (round/quizmaster/participants/winner)
via its public CSV export - no auth needed, the sheet is link-shared - and
cache it to config/gauntlet_tracker.json. Called automatically on every
`pipeline.py export` (see pipeline.py's _maybe_refresh_gauntlet_tracker);
run directly for a one-off refresh:

    python3 utils/fetch_gauntlet_tracker.py
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import requests

SHEET_ID = "1AeyYvUADeajkd_WOnH9wsI3N-mZbswpFcdypzVb2kBc"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"
BLOCK_WINDOW_GAUNTLETS = 5


def _parse_rows(rows: list[list[str]]) -> list[dict]:
    """
    Sheet layout: one banner row, one column-header row, then 4 rows per
    gauntlet (one per participant). Gauntlet No/QM/Winner are merged cells in
    the sheet and only appear on the first of the 4 rows once exported to
    CSV (blank on the other 3) - forward-fill those within each block.
    """
    rounds: list[dict] = []
    cur: dict | None = None
    for row in rows[2:]:
        cells = (row + ["", "", "", ""])[:4]
        gnum, qm, participant, winner = (c.strip() for c in cells)
        if not any((gnum, qm, participant, winner)):
            continue
        if gnum:
            if cur is not None:
                rounds.append(cur)
            cur = {"round": int(gnum), "quizmaster": qm, "participants": [], "winner": winner}
        if participant and cur is not None:
            cur["participants"].append(participant)
    if cur is not None:
        rounds.append(cur)
    return rounds


def fetch_and_cache(cache_path: Path) -> dict:
    resp = requests.get(CSV_URL, timeout=15)
    resp.raise_for_status()
    rows = list(csv.reader(io.StringIO(resp.text)))
    rounds = _parse_rows(rows)
    if not rounds:
        raise ValueError("Parsed 0 gauntlet rounds - sheet layout may have changed")
    data = {
        "_comment": (
            "Auto-fetched from the 'Gauntlet Tracker' Google Sheet on every "
            "pipeline.py export (see fetch_gauntlet_tracker.py) - don't hand-edit, "
            "it gets overwritten on the next successful fetch."
        ),
        "source_url": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
        "block_window_gauntlets": BLOCK_WINDOW_GAUNTLETS,
        "rounds": rounds,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def main() -> None:
    cache_path = Path(__file__).parent.parent / "config" / "gauntlet_tracker.json"
    data = fetch_and_cache(cache_path)
    print(f"Wrote {cache_path} - {len(data['rounds'])} gauntlet rounds")


if __name__ == "__main__":
    main()
