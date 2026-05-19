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
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

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

# ── Chat parsing ─────────────────────────────────────────────────────────────

def parse_chat_messages(chat_text: str) -> list[dict]:
    """Delegate to stage1 for correct timezone handling and alias normalisation.
    Returns messages with `timestamp` (UTC ISO Z), `username`, `text`, `date`
    (UTC date derived from the timestamp), `has_media`."""
    sys.path.insert(0, str(PIPELINE_DIR))
    from utils.config import load_config, load_aliases
    from stages.stage1_parse import run as stage1_run

    config = dict(load_config(CONFIG_DIR))
    aliases = load_aliases(CONFIG_DIR)
    lines = chat_text.splitlines()
    raw_msgs = stage1_run(lines, config, aliases)
    out: list[dict] = []
    for m in raw_msgs:
        ts = m.get("timestamp")
        if hasattr(ts, "strftime"):
            iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            date = ts.strftime("%Y-%m-%d")
        else:
            iso = str(ts)
            date = iso[:10]
        out.append({
            "timestamp": iso,
            "username": m.get("username", ""),
            "text": m.get("text", ""),
            "date": date,
            "has_media": m.get("has_media", False),
        })
    return out


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
            f"{{\"batch_id\": \"{batch_id}\", \"extracted\": [<full schema entries>], "
            f"\"_provenance_method\": \"me-as-llm-fork\", \"_provenance_model\": \"claude-opus-4-7\"}}. "
            f"Each entry must conform to the existing extraction_output schema "
            f"(question_timestamp, question_text, question_asker, topics, has_media, "
            f"is_session_question + session_* fields, answer_text + answer_solver + "
            f"answer_timestamp, answer_confirmed, confirmation_text, "
            f"answer_is_collaborative, answer_parts, discussion[], scores_after, "
            f"extraction_confidence). Apply STRONG-signal rules and the cross-asker / "
            f"image-trigger / connect-quiz rules. Return ONLY the dates listed; ignore others.\n\n"
            f"RECALL-FIRST DIRECTIVE: Missing a Q is the worst outcome. Missing the answer "
            f"on a captured Q is acceptable (set extraction_confidence=low). When in doubt, "
            f"include the Q.\n\n"
            f"PROCESS THE ENTIRE DATE END-TO-END:\n"
            f"  - Walk messages in 200-msg windows from index 0 to the last message.\n"
            f"  - Do NOT stop after the first few hours. Quiz activity continues all day.\n"
            f"  - Sanity check: timestamp range of extracted Qs should span the chat's "
            f"active hours, not just the morning.\n\n"
            f"PATTERNS TO CATCH (commonly missed):\n"
            f"  1. Mini-round rapid-fire: when one asker posts a numbered list of items "
            f"(e.g. '1. Sachhai Ka Jaal', '2. Balle balle...') with the group guessing "
            f"each, treat EACH numbered item as a separate Q. Asker = poster. Solver = "
            f"first correct guesser confirmed by asker.\n"
            f"  2. Image-trigger Qs: an image + a short prompt ('Pehchaan kaun?', "
            f"'What movie?', 'Connect:') is a Q even without '?'. has_media=true.\n"
            f"  3. Multi-hint Qs: one asker posts question + N follow-up hints over "
            f"minutes. Bundle as ONE Q (question_text concatenated with hints).\n"
            f"  4. Cross-asker session continuation: when session host pauses ('back in 5') "
            f"and resumes later, continue extracting Qs into same session_id.\n"
            f"  5. Dialogue/title guess games: 'Guess this dialogue: ...' or 'What movie: "
            f"...' is a Q. Answer = correctly guessed source.\n"
            f"  6. Self-revealed answers: if asker reveals answer after group fails, still "
            f"a Q (answer_confirmed=false, answer_solver=null, answer_text=reveal, "
            f"extraction_confidence=medium; put reveal in discussion[] with role=answer_reveal).\n\n"
            f"REJECTED LOG: include a `rejected` array alongside `extracted` for "
            f"candidates you considered but excluded, with one-line reasons. Helps audit."
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

    # Provenance: record each date with extraction method. Method is read from
    # output.json `_provenance_method` if set by the LLM responder (forks set
    # "me-as-llm-fork"); fallback to "me-as-llm-inline" for legacy/inline runs.
    try:
        from utils import provenance
        if "_provenance_method" not in out:
            log.warning(
                "[%s] output.json missing _provenance_method — defaulting to 'me-as-llm-inline'. "
                "If this was a fork run, the fork forgot to self-tag. Check the prompt.",
                batch_dir.name,
            )
        method = out.get("_provenance_method", "me-as-llm-inline")
        model = out.get("_provenance_model")
        notes = out.get("_provenance_notes")
        for date, entries in by_date.items():
            provenance.record(date, method=method, model=model, count=len(entries), notes=notes)
    except Exception as e:
        log.warning("[%s] Provenance record failed: %s", batch_dir.name, e)

    # Density sanity check: warn if msgs/Q ratio is outlier vs the recall-fix
    # neighbor band (target 20-50 msgs/Q). Caught the original 11-06 baseline at
    # 96 msgs/Q would have been flagged here.
    for date, entries in by_date.items():
        date_msgs = [m for m in inp.get("messages", []) if m.get("date") == date]
        n_msgs = len(date_msgs)
        n_qs = len(entries)
        if n_qs == 0:
            log.warning("[%s] DENSITY ALERT: 0 Qs extracted from %d msgs", date, n_msgs)
            continue
        ratio = n_msgs / n_qs
        if ratio > 60:
            log.warning(
                "[%s] DENSITY ALERT: %d msgs / %d Qs = %.0f msgs/Q "
                "(target 20-50). Likely under-extraction — verify recall.",
                date, n_msgs, n_qs, ratio,
            )
        elif ratio < 8:
            log.warning(
                "[%s] DENSITY ALERT: %d msgs / %d Qs = %.0f msgs/Q "
                "(target 20-50). Likely over-extraction — verify precision.",
                date, n_msgs, n_qs, ratio,
            )
        else:
            log.info("[%s] density ok: %d msgs / %d Qs = %.0f msgs/Q", date, n_msgs, n_qs, ratio)

    log.info("[%s] Finalized.", batch_dir.name)


def _run_stages_for_dates(dates: list[str]) -> None:
    """Run auto-fix + stages 3-6 for the given dates without invoking the LLM."""
    sys.path.insert(0, str(PIPELINE_DIR))
    from utils.config import load_config
    from utils.auto_fix import apply_auto_fixes
    from utils.audit_extraction import audit_data
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

    # Clean stale FTS rows from any prior wipes — DELETE FROM questions doesn't
    # cascade to the questions_fts virtual table, and stage5's FTS insert will
    # hit a UNIQUE constraint if a stale row still references the same `id`.
    with sqlite3.connect(str(DB_PATH)) as db:
        stale = db.execute(
            "DELETE FROM questions_fts WHERE rowid NOT IN (SELECT rowid FROM questions)"
        ).rowcount
        if stale:
            log.info("Cleaned %d stale FTS row(s) before stage5", stale)
        db.commit()

    # Parse chat once for rejected_candidates writing.
    by_date: dict[str, list[dict]] = {}
    if CHAT_FILE.exists():
        msgs = parse_chat_messages(CHAT_FILE.read_text(encoding="utf-8", errors="replace"))
        for m in msgs:
            d = m["date"]
            if d in dates:
                by_date.setdefault(d, []).append(m)

    rejected_dir = DATA_DIR / "attribution_gaps" / "rejected_candidates"
    rejected_json = output_dir / "rejected_candidates.json"

    # Lazy imports for optional steps (skipped on error).
    try:
        from pipeline import _write_rejected_candidates
    except ImportError:
        _write_rejected_candidates = None
    try:
        from utils.export_rejected import export_rejected as _export_rejected
    except ImportError:
        _export_rejected = None

    for date in dates:
        path = EXTRACTION_DIR / f"{date}.json"
        if not path.exists():
            continue
        candidates = json.loads(path.read_text(encoding="utf-8"))
        # Auto-fix first — same normalisation that stage 2 applies post-LLM.
        fixes = apply_auto_fixes(candidates, config_dir=CONFIG_DIR)
        if fixes:
            log.info("  [%s] Auto-fixed %d issue(s) before stages 3-6", date, fixes)
            path.write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
        # Audit — log any issues remaining (informational only)
        remaining = audit_data(candidates)
        if remaining:
            log.warning("  [%s] %d audit issue(s) remain after auto-fix:", date, len(remaining))
            for issue in remaining[:10]:
                log.warning("    %s", issue)
        questions = stage3(candidates, config, errors_dir=errors_dir)
        questions = [q for q in questions if str(q.date) == date]
        if not questions:
            continue
        questions = stage4(questions, config, llm_client=None)  # skip LLM enrichment; AI already provided topics
        with sqlite3.connect(str(DB_PATH)) as db:
            stage5(questions, db, state_path=state_path)

        # Per-date rejected candidates (matches backfill behavior)
        if _write_rejected_candidates and date in by_date:
            try:
                _write_rejected_candidates({date: by_date[date]}, EXTRACTION_DIR, rejected_dir, config)
            except Exception as e:
                log.warning("  [%s] rejected_candidates write skipped: %s", date, e)

    # Re-export DB once after all dates
    with sqlite3.connect(str(DB_PATH)) as db:
        stage6(db, output_dir, members_config_path=members_cfg,
               session_overrides_path=sess_overrides, state_path=state_path)

    # Refresh combined rejected_candidates.json for the visualizer
    if _export_rejected and rejected_dir.exists():
        try:
            _export_rejected(rejected_dir, rejected_json)
            log.info("Refreshed %s", rejected_json.name)
        except Exception as e:
            log.warning("export_rejected skipped: %s", e)

    # Per-date media match (matches backfill behavior)
    media_dir = V2_DIR / "data" / "raw"
    if media_dir.is_dir():
        try:
            from utils.media_match import match_media
            from stages.stage5_store import upsert as _upsert
            for date in dates:
                with sqlite3.connect(str(DB_PATH)) as db:
                    rows = db.execute(
                        "SELECT payload FROM questions WHERE date=? AND has_media=1", (date,)
                    ).fetchall()
                if not rows:
                    continue
                # Re-load Q objects through stage 3 so media matching can write back
                ext_path = EXTRACTION_DIR / f"{date}.json"
                if not ext_path.exists():
                    continue
                cands = json.loads(ext_path.read_text(encoding="utf-8"))
                qs = stage3(cands, config, errors_dir=errors_dir)
                qs_media = [q for q in qs if q.question.has_media and q.question.media is None]
                if not qs_media:
                    continue
                enriched = match_media(qs_media, media_dir, config)
                matched = [q for q in enriched if q.question.media is not None]
                if matched:
                    with sqlite3.connect(str(DB_PATH)) as db:
                        _upsert(matched, db)
                    log.info("  [%s] Matched %d media files", date, len(matched))
            # Re-export so static/data picks up media URLs
            with sqlite3.connect(str(DB_PATH)) as db:
                stage6(db, output_dir, members_config_path=members_cfg,
                       session_overrides_path=sess_overrides, state_path=state_path)
        except Exception as e:
            log.warning("enrich-media skipped: %s", e)

    # Session images (idempotent — only generates for new sessions)
    try:
        from utils.generate_session_images import main as _gen_images_main
        old_argv = sys.argv
        sys.argv = [sys.argv[0]]
        _gen_images_main()
        sys.argv = old_argv
        log.info("Session images pass complete")
    except SystemExit:
        pass
    except Exception as e:
        log.warning("generate-images skipped: %s", e)


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
