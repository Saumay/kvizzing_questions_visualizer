"""
Run Stage 4 LLM enrichment on just the questions missing tags in a given
date range, via LLM_PROVIDER=claude_file (no Gemini key needed).

Why not plain `reenrich`: it selects by topic count (< 2 topics), but these
questions already have topics from the rule-based `assign-topics` pass —
only tags are missing. `fresh=True` forces every selected question through
the LLM regardless of topic count; the LLM's topic judgment is generally
better than the rule-based fallback anyway, so this also upgrades topics.

Usage (run from v2/, with LLM_PROVIDER=claude_file set):
    LLM_PROVIDER=claude_file python3 pipeline/utils/fill_tags_jfm.py 2026-01-01 2026-01-02 ...
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent.parent
V2_DIR = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

from utils.config import load_config
from stages.stage4_enrich import enrich as stage4_enrich
from stages.stage5_store import load_all, upsert
from stages.stage6_export import run as stage6_export_run
from clients.llm import get_client


def main() -> None:
    dates = set(sys.argv[1:])
    if not dates:
        print(__doc__)
        sys.exit(1)

    config = load_config(PIPELINE_DIR / "config")
    db_path = V2_DIR / "data" / "questions.db"
    output_dir = V2_DIR / "visualizer" / "static" / "data"

    client = get_client()
    if client is None:
        print("No LLM client available — set LLM_PROVIDER=claude_file or GEMINI_API_KEY.")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    all_questions = load_all(conn)
    target = [q for q in all_questions if q.date.isoformat() in dates]
    needs = [q for q in target if not q.question.tags]
    print(f"{len(target)} questions in the target dates, {len(needs)} missing tags.")

    if not needs:
        print("Nothing to do.")
        conn.close()
        return

    enriched = stage4_enrich(needs, config, client, fresh=True)
    gained = sum(1 for q in enriched if q.question.tags)
    print(f"{gained}/{len(needs)} now have tags.")

    upsert(enriched, conn)
    print("Re-exporting JSON files…")
    stage6_export_run(
        conn, output_dir,
        members_config_path=PIPELINE_DIR / "config" / "members.json",
        session_overrides_path=PIPELINE_DIR / "config" / "session_overrides.json",
        state_path=V2_DIR / "data" / "pipeline_state.json",
    )
    conn.close()
    print("fill_tags_jfm complete.")


if __name__ == "__main__":
    main()
