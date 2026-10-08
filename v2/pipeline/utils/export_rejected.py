"""
Combine per-date rejected-candidate JSON files from data/attribution_gaps/rejected_candidates/
into a lightweight index plus monthly-sharded body files for the review UI.

Each per-date file contains a JSON array of thread objects.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

log = logging.getLogger("kvizzing")


def export_rejected(
    rejected_dir: Path,
    output_dir: Path,
    extracted_timestamps: dict[str, str] | None = None,
) -> int:
    """Combine all per-date thread files into a lightweight index
    (`rejected_index.json`) plus monthly shard files
    (`rejected_candidates_<YYYY-MM>.json`) under `output_dir`. Returns the
    total thread count.

    Threads are never dropped. If `extracted_timestamps` (a map of question
    timestamp -> question id) is given, threads whose candidates were later
    promoted into the archive are tagged `extracted`/`extracted_id` instead of
    being removed, so the review UI can still show the checkmark badge and
    keep the audit trail intact.
    """
    extracted_timestamps = extracted_timestamps or {}
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

    index: list[dict] = []
    by_month: dict[str, list[dict]] = defaultdict(list)
    for t in all_entries:
        cands = t.get("candidates", [])
        tagged_cands = []
        extracted = False
        for c in cands:
            qid = extracted_timestamps.get(c.get("timestamp"))
            if qid:
                c = {**c, "extracted_id": qid}
                extracted = True
            tagged_cands.append(c)
        t = {**t, "candidates": tagged_cands, "extracted": extracted}

        month = t["date"][:7]  # YYYY-MM
        by_month[month].append(t)
        index.append({
            "id": t["id"],
            "date": t["date"],
            "candidate_count": len(cands),
            "extracted": extracted,
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "rejected_index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    for month, threads in by_month.items():
        (output_dir / f"rejected_candidates_{month}.json").write_text(
            json.dumps(threads, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return len(all_entries)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Export rejected candidates to an index + monthly shards")
    parser.add_argument("--rejected-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    v2_dir = Path(__file__).resolve().parent.parent.parent
    rejected_dir = args.rejected_dir or v2_dir / "data" / "attribution_gaps" / "rejected_candidates"
    output_dir = args.output_dir or v2_dir / "visualizer" / "static" / "data"
    count = export_rejected(rejected_dir, output_dir)
    print(f"Wrote {count} thread(s) to {output_dir} (index + monthly shards)")


if __name__ == "__main__":
    main()
