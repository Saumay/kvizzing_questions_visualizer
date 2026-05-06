"""
Build a review-suggest input bundle for AI-assisted classification of
unreviewed rejected candidate threads.

Pipeline:
  1. fetch_votes()         — pull all votes from Supabase (anon key, public).
  2. build_curator_labels() — collapse to curator-trusted decisions.
  3. build_input_bundle()  — emit a single JSON file an AI reviewer can read,
                             classify, and write back as auto_review_suggestions.json.
  4. write_outputs_from_classifications() — assemble the final suggestions
                             file from classifications + copy to static/data.

Curators are listed in config/curators.json. Their votes win on conflict
(most-recent timestamp). All other reviewers' votes are kept as low-trust
"context notes" attached to each unreviewed thread.

Threads already extracted into the questions DB are excluded — the UI
already marks those with a synthetic self-vote (✓ Extracted).

The actual classification step (assigning suggested status + reason +
confidence per thread) is performed by the AI reviewer (Claude in the
session), not by this script. This script only prepares input and
finalises output.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("kvizzing")

V2_DIR = Path(__file__).resolve().parent.parent.parent
PIPELINE_DIR = V2_DIR / "pipeline"
DATA_DIR = V2_DIR / "data"
REJECTED_DIR = DATA_DIR / "attribution_gaps" / "rejected_candidates"
EXTRACTION_DIR = DATA_DIR / "extraction_output"
DB_PATH = DATA_DIR / "questions.db"
STATIC_DATA = V2_DIR / "visualizer" / "static" / "data"

# Public Supabase config (mirrors visualizer/src/lib/supabase.ts).
# Safe to embed: it's the publishable anon key, already shipped in the static bundle.
SUPABASE_URL = "https://agquxbdhrvqisjgljrhm.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_kTrC7PoqosRc7jjcCgp-Rg_4IZ--0ZF"


# ── Curator config ──────────────────────────────────────────────────────────

def load_curators(config_dir: Optional[Path] = None) -> set[str]:
    config_dir = config_dir or PIPELINE_DIR / "config"
    cfg = json.loads((config_dir / "curators.json").read_text(encoding="utf-8"))
    return set(cfg["curators"])


# ── Supabase access ─────────────────────────────────────────────────────────

def fetch_votes() -> list[dict]:
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/votes?select=*",
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ── Label building ──────────────────────────────────────────────────────────

def build_curator_labels(votes: list[dict], curators: set[str]) -> dict[str, dict]:
    """thread_id → { status, reason, voter, ts } using the most-recent curator vote."""
    out: dict[str, dict] = {}
    for v in votes:
        if v["reviewer"] not in curators:
            continue
        ts = v.get("created_at") or v.get("updated_at") or ""
        prev = out.get(v["thread_id"])
        if prev and prev.get("ts", "") > ts:
            continue
        out[v["thread_id"]] = {
            "status": v["status"],
            "reason": v.get("reason") or "",
            "voter": v["reviewer"],
            "ts": ts,
        }
    return out


def build_other_notes(votes: list[dict], curators: set[str]) -> dict[str, list[dict]]:
    """thread_id → [ { reviewer, status, reason } ] for non-curator votes."""
    out: dict[str, list[dict]] = {}
    for v in votes:
        if v["reviewer"] in curators:
            continue
        out.setdefault(v["thread_id"], []).append({
            "reviewer": v["reviewer"],
            "status": v["status"],
            "reason": v.get("reason") or "",
        })
    return out


# ── Rejected threads + extraction cross-ref ─────────────────────────────────

def load_rejected_threads(rejected_dir: Path = REJECTED_DIR) -> list[dict]:
    threads: list[dict] = []
    for f in sorted(rejected_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for t in data:
                if t.get("candidates"):
                    threads.append(t)
        except Exception as e:
            log.warning("Failed to read %s: %s", f.name, e)
    return threads


def extracted_timestamps(db_path: Path = DB_PATH) -> set[str]:
    if not db_path.exists():
        return set()
    out: set[str] = set()
    with sqlite3.connect(str(db_path)) as conn:
        for (payload,) in conn.execute("SELECT payload FROM questions"):
            try:
                p = json.loads(payload)
                ts = p.get("question", {}).get("timestamp")
                if ts:
                    out.add(ts)
            except Exception:
                continue
    return out


def is_thread_extracted(thread: dict, ts_set: set[str]) -> bool:
    return any(c.get("timestamp") in ts_set for c in thread.get("candidates", []))


# ── Few-shot example pool (for AI reviewer to consult) ─────────────────────

def build_few_shot_pool(
    curator_labels: dict[str, dict],
    threads_by_id: dict[str, dict],
    per_class: int = 6,
) -> list[dict]:
    """Pick a balanced set of curator-labeled threads as anchors for the AI reviewer.
    Includes the candidate text, reason, and a short context window.
    """
    by_status: dict[str, list[dict]] = {"valid": [], "maybe": [], "not_valid": []}
    for tid, lab in curator_labels.items():
        t = threads_by_id.get(tid)
        if not t:
            continue
        by_status[lab["status"]].append({
            "thread_id": tid,
            "date": t.get("date", ""),
            "candidates": [
                {"timestamp": c["timestamp"], "username": c["username"], "text": c["text"]}
                for c in t.get("candidates", [])
            ],
            "context_excerpt": _context_excerpt(t),
            "curator_status": lab["status"],
            "curator_reason": lab["reason"],
            "curator_voter": lab["voter"],
        })
    # Deterministic order: latest first by date+id
    out = []
    for s in ("valid", "not_valid", "maybe"):
        items = sorted(by_status[s], key=lambda x: (x["date"], x["thread_id"]), reverse=True)
        out.extend(items[:per_class])
    return out


def _context_excerpt(thread: dict, before: int = 4, after: int = 4) -> list[dict]:
    """Window of context messages around the candidates."""
    ctx = thread.get("context", [])
    if not ctx:
        return []
    cand_idxs = [i for i, m in enumerate(ctx) if m.get("is_candidate")]
    if not cand_idxs:
        return [{"timestamp": m["timestamp"], "username": m["username"], "text": m["text"][:200]}
                for m in ctx[-8:]]
    lo = max(0, cand_idxs[0] - before)
    hi = min(len(ctx), cand_idxs[-1] + after + 1)
    return [
        {"timestamp": m["timestamp"], "username": m["username"], "text": m["text"][:200],
         "is_candidate": m.get("is_candidate", False)}
        for m in ctx[lo:hi]
    ]


# ── Bundle assembly ─────────────────────────────────────────────────────────

def build_input_bundle(
    votes: list[dict],
    threads: list[dict],
    extracted_ts: set[str],
    curators: set[str],
) -> dict:
    threads_by_id = {t["id"]: t for t in threads}
    curator_labels = build_curator_labels(votes, curators)
    other_notes = build_other_notes(votes, curators)
    few_shot = build_few_shot_pool(curator_labels, threads_by_id)

    unreviewed: list[dict] = []
    for t in threads:
        if t["id"] in curator_labels:
            continue
        if is_thread_extracted(t, extracted_ts):
            continue
        unreviewed.append({
            "thread_id": t["id"],
            "date": t.get("date", ""),
            "candidates": [
                {"timestamp": c["timestamp"], "username": c["username"],
                 "text": c["text"], "reason_flagged": c.get("reason_flagged", "")}
                for c in t.get("candidates", [])
            ],
            "context_excerpt": _context_excerpt(t),
            "other_reviewer_notes": other_notes.get(t["id"], []),
        })

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "curators": sorted(curators),
        "stats": {
            "total_votes": len(votes),
            "curator_labels": len(curator_labels),
            "extracted_threads": sum(1 for t in threads if is_thread_extracted(t, extracted_ts)),
            "unreviewed": len(unreviewed),
            "valid_anchors": sum(1 for x in few_shot if x["curator_status"] == "valid"),
            "not_valid_anchors": sum(1 for x in few_shot if x["curator_status"] == "not_valid"),
            "maybe_anchors": sum(1 for x in few_shot if x["curator_status"] == "maybe"),
        },
        "few_shot_examples": few_shot,
        "unreviewed_threads": unreviewed,
        "instructions_for_ai_reviewer": (
            "For each thread in unreviewed_threads, decide whether it contains a "
            "trivia question that the LLM extractor missed (status=valid / Missed Q), "
            "is genuinely not a question (status=not_valid / Not a Q), or is "
            "ambiguous (status=maybe). Use few_shot_examples as calibration. "
            "Lean Not-a-Q unless the candidate has clear trivia structure. Output "
            "format: an array of { thread_id, status, reason, confidence (0..1) }. "
            "Pick reasons from the curator's preset vocabulary when applicable: "
            "valid -> 'Genuine trivia question'; "
            "not_valid -> 'Casual conversation', 'Discussion after a question', "
            "'Guess/answer attempt', 'Quiz logistics/coordination', "
            "'Rhetorical question', 'Answer reveal/additional trivia after a question', "
            "'Session announcement', 'Bonus/follow-up question'. "
            "Custom reasons are OK when none fit."
        ),
    }


# ── Output ──────────────────────────────────────────────────────────────────

def write_input_bundle(bundle: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")


def merge_classifications_to_suggestions(
    classifications: list[dict],
    curator_labels: dict[str, dict],
    min_confidence: float = 0.0,
) -> list[dict]:
    """Drop any classification that overlaps a curator vote (curator wins) or
    falls below min_confidence. Returns suggestions array ready for the UI."""
    out = []
    for c in classifications:
        if c["thread_id"] in curator_labels:
            continue
        if c.get("confidence", 0) < min_confidence:
            continue
        out.append({
            "thread_id": c["thread_id"],
            "status": c["status"],
            "reason": c.get("reason", ""),
            "confidence": c.get("confidence", 0),
            "source": "ai",
        })
    return out


# ── CLI ─────────────────────────────────────────────────────────────────────

def cmd_prepare(args: argparse.Namespace) -> int:
    curators = load_curators()
    log.info("Curators: %s", ", ".join(sorted(curators)))
    votes = fetch_votes()
    log.info("Pulled %d votes from Supabase.", len(votes))
    threads = load_rejected_threads()
    log.info("Loaded %d rejected threads.", len(threads))
    if args.date:
        threads = [t for t in threads if t.get("date") == args.date]
        log.info("Filtered to date %s: %d threads.", args.date, len(threads))
    ext_ts = extracted_timestamps()
    log.info("DB has %d extracted question timestamps.", len(ext_ts))

    bundle = build_input_bundle(votes, threads, ext_ts, curators)
    log.info(
        "Bundle: %d unreviewed, %d curator-labelled, %d extracted, %d anchors "
        "(valid=%d / not_valid=%d / maybe=%d)",
        bundle["stats"]["unreviewed"], bundle["stats"]["curator_labels"],
        bundle["stats"]["extracted_threads"],
        len(bundle["few_shot_examples"]),
        bundle["stats"]["valid_anchors"], bundle["stats"]["not_valid_anchors"],
        bundle["stats"]["maybe_anchors"],
    )

    out_path = Path(args.output) if args.output else DATA_DIR / "review_input.json"
    write_input_bundle(bundle, out_path)
    log.info("Wrote %s", out_path)
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    """Take a classifications JSON (produced by the AI reviewer) and merge it
    into the final suggestions file + copy to static/data for the UI."""
    classifications_path = Path(args.classifications)
    classifications = json.loads(classifications_path.read_text(encoding="utf-8"))
    if isinstance(classifications, dict):
        classifications = classifications.get("classifications", [])

    curators = load_curators()
    votes = fetch_votes()
    curator_labels = build_curator_labels(votes, curators)

    suggestions = merge_classifications_to_suggestions(
        classifications, curator_labels, min_confidence=args.min_confidence,
    )

    out_local = DATA_DIR / "auto_review_suggestions.json"
    out_static = STATIC_DATA / "auto_review_suggestions.json"
    archive_dir = DATA_DIR / "ai_classifications"
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "min_confidence": args.min_confidence,
        "count": len(suggestions),
        "suggestions": suggestions,
    }
    out_local.parent.mkdir(parents=True, exist_ok=True)
    out_static.parent.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    out_local.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    out_static.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    # Archive a timestamped copy of the raw classifications input (audit trail).
    archive_path = archive_dir / f"classifications-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
    archive_path.write_text(classifications_path.read_text(encoding="utf-8"), encoding="utf-8")
    log.info("Wrote %d suggestions to %s and %s", len(suggestions), out_local, out_static)
    log.info("Archived raw classifications to %s", archive_path)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("prepare", help="Build the input bundle for AI-assisted classification.")
    pp.add_argument("--date", help="Restrict to one date (YYYY-MM-DD).")
    pp.add_argument("--output", help="Write bundle to this path (default: v2/data/review_input.json).")
    pp.set_defaults(func=cmd_prepare)
    pf = sub.add_parser("finalize", help="Merge AI classifications into the final suggestions file.")
    pf.add_argument("--classifications", required=True, help="Path to JSON array of {thread_id, status, reason, confidence}.")
    pf.add_argument("--min-confidence", type=float, default=0.6)
    pf.set_defaults(func=cmd_finalize)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
