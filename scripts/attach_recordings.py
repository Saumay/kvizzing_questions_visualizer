"""
Patch v2/visualizer/static/data/decks.json in place: attach video recording
links (from video_recordings.py / video_recordings_raw.csv) to existing
rounds/decks, and add the sessions that only have a recording with no deck
file at all.

Idempotent: skips a recording if a file with the same url is already
present, so it's safe to rerun after adding new rows to the CSV.

Patches decks.json directly instead of going through
build_decks_manifest.py, because that script always resets every file's
`url` to null (it expects the R2 upload step to fill them in) — rerunning
it here would wipe out already-uploaded slide URLs. Recording URLs are
known upfront (they're not going through R2), so there's no such hazard
for them specifically.
"""

from __future__ import annotations

import json
from pathlib import Path

from video_recordings import (
    ATTACH,
    NEW_GAUNTLET_ROUNDS,
    NEW_SERIES,
    NEW_STANDALONE,
    OLD_SCHOOL_PARTS,
    _recording_file,
    load_urls_by_row_index,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DECKS_JSON = REPO_ROOT / "v2" / "visualizer" / "static" / "data" / "decks.json"
CSV_PATH = Path(__file__).parent / "video_recordings_raw.csv"


def _has_url(files: list[dict], url: str) -> bool:
    return any(f.get("url") == url for f in files)


def main() -> None:
    urls = load_urls_by_row_index(CSV_PATH)
    manifest = json.loads(DECKS_JSON.read_text())

    series_by_id = {s["id"]: s for s in manifest["series"]}
    standalone_by_id = {d["id"]: d for d in manifest["standalone"]}

    attached = 0
    for (kind, ident, round_num), row in ATTACH:
        url = urls[row]
        if kind == "series":
            s = series_by_id[ident]
            r = next(r for r in s["rounds"] if r["round"] == round_num)
            if not _has_url(r["files"], url):
                r["files"].append(_recording_file(url))
                attached += 1
        else:
            d = standalone_by_id[ident]
            if not _has_url(d["files"], url):
                d["files"].append(_recording_file(url))
                attached += 1

    # Gauntlet round 14: fill in host from the "LZA" recording folder name.
    gauntlet = series_by_id["gauntlet"]
    r14 = next(r for r in gauntlet["rounds"] if r["round"] == 14)
    if r14["host"] is None:
        r14["host"] = "Lzafeer"

    # Old School Quiz: two recording parts alongside the single existing PDF.
    old_school = standalone_by_id["old-school-kp"]
    for row, label in OLD_SCHOOL_PARTS:
        url = urls[row]
        if not _has_url(old_school["files"], url):
            old_school["files"].append(_recording_file(url, label))
            attached += 1

    # New Gauntlet rounds (recording only, no deck).
    added_rounds = 0
    for spec in NEW_GAUNTLET_ROUNDS:
        if any(r["round"] == spec["round"] for r in gauntlet["rounds"]):
            continue
        gauntlet["rounds"].append({
            "round": spec["round"], "title": spec["title"], "host": spec["host"],
            "date": spec["date"], "date_approx": spec["date_approx"],
            "files": [_recording_file(urls[spec["row"]])],
        })
        added_rounds += 1
    gauntlet["rounds"].sort(key=lambda r: r["round"])

    # New series (recording-only sessions grouped like a mini-tournament).
    added_series = 0
    for spec in NEW_SERIES:
        if spec["id"] in series_by_id:
            continue
        manifest["series"].append({
            "id": spec["id"], "title": spec["title"], "description": spec["description"],
            "rounds": [
                {
                    "round": r["round"], "title": r["title"], "host": r["host"],
                    "date": r["date"], "date_approx": r["date_approx"],
                    "files": [_recording_file(urls[r["row"]])],
                }
                for r in spec["rounds"]
            ],
        })
        added_series += 1

    # New standalone recording-only sessions.
    added_standalone = 0
    for spec in NEW_STANDALONE:
        if spec["id"] in standalone_by_id:
            continue
        manifest["standalone"].append({
            "id": spec["id"], "title": spec["title"], "host": spec["host"],
            "date": spec["date"], "date_approx": spec["date_approx"],
            "files": [_recording_file(urls[spec["row"]])],
        })
        added_standalone += 1

    DECKS_JSON.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Attached {attached} recording(s) to existing decks/rounds.")
    print(f"Added {added_rounds} new Gauntlet round(s).")
    print(f"Added {added_series} new series.")
    print(f"Added {added_standalone} new standalone session(s).")


if __name__ == "__main__":
    main()
