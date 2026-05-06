"""promote-rejected: rescue a curator-confirmed Missed Q from rejected_candidates
into the archive.

Workflow:
  1. Locate the thread by thread_id in v2/data/attribution_gaps/rejected_candidates/
  2. Build a focused single-Q LLM input (chat slice around the candidate + few-shot
     anchors) and write to v2/data/extract_batches/promote-<thread-id>/input.json
  3. AI reviewer (Claude in conversation) reads input.json, writes output.json
     with the extraction JSON entry.
  4. This script (re-invoked) finalizes: appends to extraction_output, reimports
     via stages 3-6, marks the rescue done.

Designed for one-click use from /review: the front-end POSTs the thread_id to a
backend handler that calls this script. For the current run, used manually
(curator runs after voting).

Usage:
    python3 pipeline.py promote-rejected --thread-id 2025-11-03-t3
    python3 pipeline.py promote-rejected --thread-id 2025-11-03-t3 --reason "Genuine trivia question"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger("kvizzing")

V2_DIR = Path(__file__).resolve().parent.parent.parent
PIPELINE_DIR = V2_DIR / "pipeline"
DATA_DIR = V2_DIR / "data"
REJECTED_DIR = DATA_DIR / "attribution_gaps" / "rejected_candidates"
EXTRACTION_DIR = DATA_DIR / "extraction_output"
DB_PATH = DATA_DIR / "questions.db"
BATCHES_DIR = DATA_DIR / "extract_batches"
CONFIG_DIR = PIPELINE_DIR / "config"


def find_thread(thread_id: str) -> tuple[Path, dict] | None:
    """Find the rejected thread by id. thread_id format: YYYY-MM-DD-tN."""
    if not thread_id or "-t" not in thread_id:
        return None
    date = thread_id.rsplit("-t", 1)[0]
    path = REJECTED_DIR / f"{date}.json"
    if not path.exists():
        return None
    threads = json.loads(path.read_text(encoding="utf-8"))
    for t in threads:
        if t.get("id") == thread_id:
            return path, t
    return None


def build_promote_input(thread: dict, reason: str, batch_id: str) -> dict:
    """Build a focused input bundle for the AI to extract this single thread."""
    return {
        "batch_id": batch_id,
        "kind": "promote_rejected",
        "thread_id": thread.get("id"),
        "date": thread.get("date"),
        "curator_reason": reason,
        "candidates": thread.get("candidates", []),
        "context": thread.get("context", []),
        "instructions_for_ai": (
            f"The curator has confirmed thread {thread['id']} as a Missed Q with reason: "
            f"\"{reason}\". Read the candidates + context. Produce ONE extracted entry "
            f"following the v2/pipeline/stages/stage2_extract.py schema. Output to "
            f"v2/data/extract_batches/{batch_id}/output.json with shape "
            f"{{\"batch_id\": \"{batch_id}\", \"extracted\": [<single entry>]}}. "
            f"Apply auto-fix consistency (confidence/confirmed pair, session orphans, "
            f"discussion order, has_media on appropriate roles only). "
            f"If multiple candidates in the thread are distinct Qs, output multiple "
            f"entries; if they're a single Q with discussion, output one entry."
        ),
    }


def finalize_promote(batch_dir: Path) -> int:
    """If output.json exists, merge into extraction_output + run stages 3-6."""
    output_path = batch_dir / "output.json"
    if not output_path.exists():
        return 0

    inp = json.loads((batch_dir / "input.json").read_text(encoding="utf-8"))
    out = json.loads(output_path.read_text(encoding="utf-8"))
    extracted = out.get("extracted", [])
    if not extracted:
        log.warning("No entries in %s — nothing to promote", output_path)
        return 0

    date = inp["date"]
    target = EXTRACTION_DIR / f"{date}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing_ts = {e.get("question_timestamp") for e in existing}
    new = [e for e in extracted if e.get("question_timestamp") not in existing_ts]
    if not new:
        log.info("All %d entries already present in %s — nothing to add", len(extracted), target.name)
        (batch_dir / ".finalized").touch()
        return 0
    merged = existing + new
    target.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Appended %d entry(ies) to %s", len(new), target.name)

    # Run stages 3-6 for this date
    sys.path.insert(0, str(PIPELINE_DIR))
    from utils.extract_loop import _run_stages_for_dates
    _run_stages_for_dates([date])

    (batch_dir / ".finalized").touch()
    return len(new)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--thread-id", required=True)
    ap.add_argument("--reason", default="Genuine trivia question")
    args = ap.parse_args()

    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    batch_id = f"promote-{args.thread_id}"
    batch_dir = BATCHES_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    # If output.json already exists from a prior call, finalize and exit.
    if (batch_dir / "output.json").exists() and not (batch_dir / ".finalized").exists():
        n = finalize_promote(batch_dir)
        log.info("Promoted %d entry(ies) for thread %s.", n, args.thread_id)
        return 0
    if (batch_dir / ".finalized").exists():
        log.info("Thread %s already promoted (batch %s finalized).", args.thread_id, batch_id)
        return 0

    # Otherwise, build input.json for the AI to read.
    found = find_thread(args.thread_id)
    if not found:
        log.error("Thread %s not found in %s", args.thread_id, REJECTED_DIR)
        return 1
    _, thread = found
    bundle = build_promote_input(thread, args.reason, batch_id)
    (batch_dir / "input.json").write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s — awaiting AI to write output.json", batch_dir / "input.json")
    log.info("After AI writes output.json, re-run: pipeline.py promote-rejected --thread-id %s", args.thread_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
