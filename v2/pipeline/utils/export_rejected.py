"""
Combine per-date rejected-candidate JSON files from data/attribution_gaps/rejected_candidates/
into a single visualizer/static/data/rejected_candidates.json.

Each per-date file contains a JSON array of thread objects.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("kvizzing")


def export_rejected(
    rejected_dir: Path,
    output_path: Path,
    extracted_timestamps: set[str] | None = None,
) -> int:
    """Combine all per-date JSON files into one array. Returns total thread count.

    If extracted_timestamps is provided, threads where any candidate's timestamp
    matches an extracted question are excluded (already in the main archive).
    """
    all_entries: list[dict] = []
    if not rejected_dir.exists():
        raise FileNotFoundError(f"Rejected candidates directory not found: {rejected_dir}")

    for json_file in sorted(rejected_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                all_entries.extend(data)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to read %s: %s", json_file.name, e)

    # Filter out threads whose candidates were already extracted as questions
    if extracted_timestamps:
        before = len(all_entries)
        all_entries = [
            t for t in all_entries
            if not any(c.get("timestamp") in extracted_timestamps for c in t.get("candidates", []))
        ]
        removed = before - len(all_entries)
        if removed:
            log.info("Excluded %d thread(s) already extracted as questions", removed)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(all_entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(all_entries)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Export rejected candidates to JSON")
    parser.add_argument("--rejected-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    v2_dir = Path(__file__).resolve().parent.parent.parent
    rejected_dir = args.rejected_dir or v2_dir / "data" / "attribution_gaps" / "rejected_candidates"
    output_path = args.output or v2_dir / "visualizer" / "static" / "data" / "rejected_candidates.json"
    count = export_rejected(rejected_dir, output_path)
    print(f"Wrote {count} thread(s) to {output_path}")


if __name__ == "__main__":
    main()
