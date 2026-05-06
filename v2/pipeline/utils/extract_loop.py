"""extract-loop: file-based async orchestrator for AI-as-LLM extraction.

Each "batch" is a directory under v2/data/extract_batches/<batch-id>/ containing:
  input.json  — written by this script (chat slice + few-shot + dates list)
  output.json — written by the AI reviewer (Claude in conversation)
  stats.txt   — written by this script after finalize

State machine (one invocation):
  1. Find batches with output.json but no .finalized marker → validate + finalize.
  2. Find next dates not yet started → write a fresh input.json. Exit.

Resumability: pick up wherever the disk says we are. No external state file —
the directory structure itself encodes progress.

Usage:
    python3 pipeline.py extract-loop                 # process whatever's pending, emit next
    python3 pipeline.py extract-loop --batch-size 2  # default 2 dates per batch
    python3 pipeline.py extract-loop --finalize-only # don't emit a new batch
    python3 pipeline.py extract-loop --emit-only     # don't finalize, just emit
    python3 pipeline.py extract-loop --status        # report progress, exit
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("kvizzing")

V2_DIR = Path(__file__).resolve().parent.parent.parent
PIPELINE_DIR = V2_DIR / "pipeline"
DATA_DIR = V2_DIR / "data"
BATCHES_DIR = DATA_DIR / "extract_batches"
EXTRACTION_DIR = DATA_DIR / "extraction_output"
DB_PATH = DATA_DIR / "questions.db"
CHAT_FILE = V2_DIR / "data" / "raw" / "_chat.txt"
CONFIG_DIR = PIPELINE_DIR / "config"

# Hard upper limit on the bulk run for this exercise (set per scope decision).
SCOPE_END_DATE = "2026-02-19"

DATE_LINE = re.compile(r"^\[(\d{1,2})/(\d{1,2})/(\d{2}), (\d{1,2}):(\d{2}):(\d{2})\] ([^:]+?): (.*)", re.DOTALL)


# ── Chat parsing ────────────────────────────────────────────────────────────

def parse_chat_messages(chat_text: str) -> list[dict]:
    """Quick parser: each message → {timestamp (UTC ISO), username, text}.
    Multi-line continuations joined with ' ↵ ' (matching stage1 convention)."""
    msgs: list[dict] = []
    current: Optional[dict] = None
    for raw in chat_text.splitlines():
        m = DATE_LINE.match(raw)
        if m:
            if current:
                msgs.append(current)
            mo, d, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hh, mm, ss = int(m.group(4)), int(m.group(5)), int(m.group(6))
            user = m.group(7).lstrip("~ ").strip()
            text = m.group(8)
            # Source timezone is America/Chicago per pipeline_config.json — but for the
            # bundle we just want a stable iso string; treat as naive and convert to Z.
            iso = f"20{yy:02d}-{mo:02d}-{d:02d}T{hh:02d}:{mm:02d}:{ss:02d}Z"
            current = {"timestamp": iso, "username": user, "text": text, "date": f"20{yy:02d}-{mo:02d}-{d:02d}"}
        else:
            # continuation of previous message
            if current is not None:
                current["text"] += " ↵ " + raw
    if current:
        msgs.append(current)
    return msgs


# ── State ─────────────────────────────────────────────────────────────────

def list_batches() -> list[Path]:
    if not BATCHES_DIR.exists():
        return []
    return sorted(p for p in BATCHES_DIR.iterdir() if p.is_dir() and p.name.startswith("batch-"))


def batch_state(batch_dir: Path) -> str:
    if (batch_dir / ".finalized").exists():
        return "finalized"
    if (batch_dir / "output.json").exists():
        return "ready"
    if (batch_dir / "input.json").exists():
        return "awaiting"
    return "empty"


def completed_dates() -> set[str]:
    """Dates already in DB OR locked into a finalized batch."""
    out: set[str] = set()
    if DB_PATH.exists():
        with sqlite3.connect(str(DB_PATH)) as conn:
            for (d,) in conn.execute("SELECT DISTINCT date FROM questions"):
                out.add(d)
    for b in list_batches():
        if (b / ".finalized").exists():
            try:
                inp = json.loads((b / "input.json").read_text(encoding="utf-8"))
                for d in inp.get("dates", []):
                    out.add(d)
            except Exception:
                continue
    return out


def in_flight_dates() -> set[str]:
    """Dates in batches that exist but aren't finalized — don't re-emit them."""
    out: set[str] = set()
    for b in list_batches():
        if (b / ".finalized").exists():
            continue
        try:
            inp = json.loads((b / "input.json").read_text(encoding="utf-8"))
            for d in inp.get("dates", []):
                out.add(d)
        except Exception:
            continue
    return out


# ── Few-shot anchor pool ────────────────────────────────────────────────────

def few_shot_anchors(n_per_kind: int = 2) -> list[dict]:
    """Pick a small mix of already-extracted Qs as calibration anchors.
    Mix: 2 standalone Qs, 2 session Qs, 2 image-Qs."""
    anchors: list[dict] = []
    standalone: list[dict] = []
    session: list[dict] = []
    image_q: list[dict] = []
    if not DB_PATH.exists():
        return anchors
    with sqlite3.connect(str(DB_PATH)) as conn:
        for (payload,) in conn.execute("SELECT payload FROM questions ORDER BY date DESC LIMIT 200"):
            try:
                p = json.loads(payload)
            except Exception:
                continue
            shaped = {
                "asker": p.get("question", {}).get("asker"),
                "text": p.get("question", {}).get("text", "")[:280],
                "is_session": bool(p.get("session")),
                "session_theme": (p.get("session") or {}).get("theme"),
                "answer": (p.get("answer") or {}).get("text"),
            }
            has_image = "[image:" in (p.get("question", {}).get("text") or "")
            if has_image and len(image_q) < n_per_kind:
                image_q.append(shaped)
            elif shaped["is_session"] and len(session) < n_per_kind:
                session.append(shaped)
            elif not shaped["is_session"] and len(standalone) < n_per_kind:
                standalone.append(shaped)
            if len(standalone) + len(session) + len(image_q) >= 3 * n_per_kind:
                break
    return standalone + session + image_q


# ── Bundle building ─────────────────────────────────────────────────────────

def pick_next_dates(batch_size: int) -> list[str]:
    """Next N dates that exist in chat, are <= SCOPE_END_DATE, not yet completed,
    and not already in flight."""
    if not CHAT_FILE.exists():
        log.error("Chat file not found at %s", CHAT_FILE)
        return []
    msgs = parse_chat_messages(CHAT_FILE.read_text(encoding="utf-8", errors="replace"))
    chat_dates = sorted({m["date"] for m in msgs if m["date"] <= SCOPE_END_DATE})
    skip = completed_dates() | in_flight_dates()
    candidates = [d for d in chat_dates if d not in skip]
    return candidates[:batch_size]


def build_input_bundle(dates: list[str], batch_id: str) -> dict:
    msgs = parse_chat_messages(CHAT_FILE.read_text(encoding="utf-8", errors="replace"))
    # Slice messages to the target dates plus 4-hour lookahead per the source-TZ rules
    # (kept simple here: just include the date's messages; stage 3+ will normalise).
    slice_msgs = [m for m in msgs if m["date"] in dates]

    return {
        "batch_id": batch_id,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "dates": dates,
        "scope_end_date": SCOPE_END_DATE,
        "few_shot_examples": few_shot_anchors(),
        "messages": slice_msgs,
        "instructions_for_ai": (
            f"Extract Q&A pairs for the listed `dates` ({', '.join(dates)}) following the "
            f"system prompt in v2/pipeline/stages/stage2_extract.py. Output to "
            f"v2/data/extract_batches/{batch_id}/output.json with shape: "
            f"{{\"batch_id\": \"{batch_id}\", \"extracted\": [<full schema entries>]}}. "
            f"Each entry must conform to the existing extraction_output schema "
            f"(question_timestamp, question_text, question_asker, topics, has_media, "
            f"is_session_question + session_* fields, answer_text + answer_solver + "
            f"answer_timestamp, answer_confirmed, confirmation_text, "
            f"answer_is_collaborative, answer_parts, discussion[], scores_after, "
            f"extraction_confidence). Apply STRONG-signal rules and the cross-asker / "
            f"image-trigger / connect-quiz rules. Do not extract clarifying or guess "
            f"messages. Return ONLY the dates listed; ignore others."
        ),
    }


# ── Finalize ────────────────────────────────────────────────────────────────

def finalize_batch(batch_dir: Path) -> None:
    """Validate output.json, write extraction_output files, run stages 3-6, mark finalized."""
    output_path = batch_dir / "output.json"
    if not output_path.exists():
        return
    inp = json.loads((batch_dir / "input.json").read_text(encoding="utf-8"))
    out = json.loads(output_path.read_text(encoding="utf-8"))
    extracted = out.get("extracted", [])
    log.info("[%s] Finalizing: %d extracted entries across %d dates",
             batch_dir.name, len(extracted), len(inp["dates"]))

    # Group by date
    by_date: dict[str, list[dict]] = {d: [] for d in inp["dates"]}
    for e in extracted:
        ts = e.get("question_timestamp", "")
        d = ts[:10]
        if d in by_date:
            by_date[d].append(e)
        else:
            log.warning("[%s] Entry with timestamp %s outside batch dates — dropping", batch_dir.name, ts)

    # Write extraction_output files
    EXTRACTION_DIR.mkdir(parents=True, exist_ok=True)
    for date, entries in by_date.items():
        path = EXTRACTION_DIR / f"{date}.json"
        # Merge with existing if any (idempotent re-run)
        existing = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing_ts = {e.get("question_timestamp") for e in existing}
        merged = existing + [e for e in entries if e.get("question_timestamp") not in existing_ts]
        path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("  wrote %s (%d entries; %d new)", path.name, len(merged), len(merged) - len(existing))

    # Run stages 3-6 via reimport (uses auto-fix + audit_extraction internally)
    sys.path.insert(0, str(PIPELINE_DIR))
    # Defer import to avoid heavy load at module import
    from utils.review_suggest import V2_DIR as _v  # noqa: F401  # ensure path

    # Use the standalone reimport-without-LLM helper inline here, since stages 3-6
    # don't need an LLM client when topics are pre-populated by the AI extractor.
    try:
        _run_stages_for_dates(list(by_date.keys()))
    except Exception as e:
        log.error("[%s] Stage 3-6 run failed: %s", batch_dir.name, e)
        raise

    # Stats
    stats = (
        f"batch_id: {batch_dir.name}\n"
        f"dates: {', '.join(inp['dates'])}\n"
        f"extracted: {len(extracted)}\n"
        f"by_date: {json.dumps({d: len(es) for d, es in by_date.items()})}\n"
        f"finalized_at: {datetime.utcnow().isoformat()}Z\n"
    )
    (batch_dir / "stats.txt").write_text(stats, encoding="utf-8")
    (batch_dir / ".finalized").touch()
    log.info("[%s] Finalized.", batch_dir.name)


def _run_stages_for_dates(dates: list[str]) -> None:
    """Run stages 3-6 for the given dates without invoking the LLM client."""
    sys.path.insert(0, str(PIPELINE_DIR))
    from utils.config import load_config
    from stages.stage3_structure import run as stage3
    from stages.stage4_enrich import run as stage4
    from stages.stage5_store import run as stage5
    from stages.stage6_export import run as stage6

    config = dict(load_config(CONFIG_DIR))
    config["chat_file"] = str(V2_DIR / config["chat_file"])
    errors_dir = DATA_DIR / "errors"
    state_path = DATA_DIR / "pipeline_state.json"
    members_cfg = CONFIG_DIR / "members.json"
    sess_overrides = CONFIG_DIR / "session_overrides.json"
    output_dir = V2_DIR / "visualizer" / "static" / "data"

    for date in dates:
        path = EXTRACTION_DIR / f"{date}.json"
        if not path.exists():
            continue
        candidates = json.loads(path.read_text(encoding="utf-8"))
        questions = stage3(candidates, config, errors_dir=errors_dir)
        questions = [q for q in questions if str(q.date) == date]
        if not questions:
            continue
        questions = stage4(questions, config, llm_client=None)  # skip LLM enrichment; topics already set
        with sqlite3.connect(str(DB_PATH)) as db:
            stage5(questions, db, state_path=state_path)
    # Re-export once after all dates
    with sqlite3.connect(str(DB_PATH)) as db:
        stage6(db, output_dir, members_config_path=members_cfg,
               session_overrides_path=sess_overrides, state_path=state_path)


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--finalize-only", action="store_true")
    ap.add_argument("--emit-only", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    BATCHES_DIR.mkdir(parents=True, exist_ok=True)

    if args.status:
        for b in list_batches():
            print(f"  {b.name}: {batch_state(b)}")
        done = completed_dates()
        print(f"\nCompleted dates (in DB or finalized): {len(done)}")
        return 0

    # 1. Finalize ready batches
    if not args.emit_only:
        for b in list_batches():
            if batch_state(b) == "ready":
                try:
                    finalize_batch(b)
                except Exception as e:
                    log.error("Finalize failed for %s: %s", b.name, e)
                    return 1

    if args.finalize_only:
        return 0

    # 2. Emit next batch
    next_dates = pick_next_dates(args.batch_size)
    if not next_dates:
        log.info("No more dates to process within scope (≤ %s).", SCOPE_END_DATE)
        return 0

    existing_ids = [b.name for b in list_batches()]
    n = 1
    while f"batch-{n:03d}" in existing_ids:
        n += 1
    batch_id = f"batch-{n:03d}"
    batch_dir = BATCHES_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    bundle = build_input_bundle(next_dates, batch_id)
    (batch_dir / "input.json").write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Emitted %s for dates %s. Awaiting output.json.", batch_id, ", ".join(next_dates))
    log.info("Input file: %s", batch_dir / "input.json")
    log.info("Expected output: %s", batch_dir / "output.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
