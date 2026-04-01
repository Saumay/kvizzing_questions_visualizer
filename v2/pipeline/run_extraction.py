#!/usr/bin/env python3
"""
run_extraction.py — LLM-powered Q&A extraction for KVizzing compact chat files.

Usage (from repo root KVizzing/):
    python3 v2/pipeline/run_extraction.py [--dates DATE [DATE ...]] [--force]

Provider is selected automatically from environment variables (same as pipeline.py):
    GEMINI_API_KEY      gemini-2.0-flash       (free tier, recommended)
    ANTHROPIC_API_KEY   claude-haiku-4-5        (~$1 for all dates)
    GROQ_API_KEY        llama-3.3-70b-versatile (free tier, low token limits)
    USE_OLLAMA=1        local Ollama model

Reads:  v2/data/extraction_compact/YYYY-MM-DD.txt
Writes: v2/data/extraction_output/YYYY-MM-DD.json
Audits: v2/pipeline/utils/audit_extraction.py after each date

Skips dates that already have an output file unless --force is passed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent  # KVizzing/
_PIPELINE_DIR = Path(__file__).parent
COMPACT_DIR = REPO_ROOT / "v2" / "data" / "extraction_compact"
OUTPUT_DIR = REPO_ROOT / "v2" / "data" / "extraction_output"

sys.path.insert(0, str(_PIPELINE_DIR))

from clients.llm import get_client
from stages.stage2_extract import _EXTRACTION_SYSTEM_PROMPT
from utils.audit_extraction import audit as _run_audit

ALL_DATES = sorted(p.stem for p in COMPACT_DIR.glob("????-??-??.txt")) if COMPACT_DIR.exists() else []

REQUEST_DELAY = 1.0  # seconds between API calls


# ── JSON parsing ───────────────────────────────────────────────────────────────

def _parse_json(text: str) -> list:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


# ── Per-date processing ────────────────────────────────────────────────────────

def process_date(date: str, llm_client, force: bool = False) -> dict:
    compact_path = COMPACT_DIR / f"{date}.txt"
    output_path = OUTPUT_DIR / f"{date}.json"

    if output_path.exists() and not force:
        print(f"  [{date}] SKIP — output already exists (use --force to re-run)")
        return {"date": date, "status": "skipped"}

    if not compact_path.exists():
        print(f"  [{date}] SKIP — compact file not found: {compact_path}")
        return {"date": date, "status": "missing_input"}

    file_content = compact_path.read_text(encoding="utf-8")
    print(f"  [{date}] {len(file_content.splitlines())} lines — calling LLM…", end=" ", flush=True)

    user_prompt = (
        f"DATE: {date}\n\n"
        f"Extract all Q&A pairs where question_timestamp starts with {date}.\n\n"
        f"=== COMPACT CHAT FILE ===\n{file_content}"
    )

    try:
        response = llm_client.messages.create(
            model="",  # ignored — client uses its own configured model
            max_tokens=8192,
            system=_EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text
    except Exception as e:
        print(f"ERROR: {e}")
        return {"date": date, "status": "llm_error", "error": str(e)}

    print("done")

    try:
        pairs = _parse_json(raw)
    except json.JSONDecodeError as e:
        print(f"  [{date}] JSON parse error: {e}")
        error_path = OUTPUT_DIR / f"{date}.error.txt"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        error_path.write_text(raw, encoding="utf-8")
        print(f"  [{date}] Raw response saved to {error_path.name}")
        return {"date": date, "status": "json_error", "error": str(e)}

    if not isinstance(pairs, list):
        print(f"  [{date}] Unexpected response type: {type(pairs)}")
        return {"date": date, "status": "bad_response"}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [{date}] Wrote {len(pairs)} Q&A pairs → {output_path.name}")

    issues = _run_audit(output_path)
    if issues:
        print(f"  [{date}] ⚠  {len(issues)} audit issue(s):")
        for issue in issues:
            print(f"        {issue}")
        return {"date": date, "status": "audit_issues", "pairs": len(pairs), "issues": issues}

    print(f"  [{date}] ✓  Audit clean")
    return {"date": date, "status": "ok", "pairs": len(pairs)}


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-powered KVizzing Q&A extraction from compact files")
    parser.add_argument(
        "--dates", nargs="+", metavar="DATE",
        help="Specific dates to process (YYYY-MM-DD). Default: all available compact files.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-run dates that already have output files.",
    )
    args = parser.parse_args()

    llm_client = get_client()
    if llm_client is None:
        print("ERROR: No LLM client available.")
        print("  Set GEMINI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY, or USE_OLLAMA=1.")
        sys.exit(1)

    dates = args.dates if args.dates else ALL_DATES
    if not dates:
        print(f"ERROR: No compact files found in {COMPACT_DIR}")
        sys.exit(1)

    print(f"KVizzing extraction — {len(dates)} date(s)")
    print("=" * 60)

    results = []
    for i, date in enumerate(dates):
        result = process_date(date, llm_client, force=args.force)
        results.append(result)
        if i < len(dates) - 1 and result["status"] not in ("skipped", "missing_input"):
            time.sleep(REQUEST_DELAY)

    print("\n" + "=" * 60)
    ok      = sum(1 for r in results if r["status"] == "ok")
    issues  = sum(1 for r in results if r["status"] == "audit_issues")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors  = sum(1 for r in results if r["status"] in ("llm_error", "json_error", "bad_response"))
    total_q = sum(r.get("pairs", 0) for r in results)

    print(f"Done.  ok={ok}  audit_issues={issues}  skipped={skipped}  errors={errors}")
    print(f"Total Q&A pairs written: {total_q}")

    if issues:
        print("\nDates with audit issues (review manually):")
        for r in results:
            if r["status"] == "audit_issues":
                print(f"  {r['date']} — {len(r['issues'])} issue(s)")

    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
