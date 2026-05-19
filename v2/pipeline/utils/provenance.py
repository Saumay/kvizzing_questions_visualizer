"""
Extraction provenance log — per-date record of HOW each date's Qs were extracted.

The pipeline and extract-loop both call `record(date, method, count, ...)` after
finalizing a date so we keep a durable audit trail of which extractor produced
which day's data. Prior runs are preserved under `history[]`.

Methods (enum):
  - "gemini"            — Gemini via pipeline backfill stage 2 LLM client
  - "me-as-llm-inline"  — Claude extracting inline in a conversation (deprecated:
                          recall drops 3-4x vs Gemini, see feedback_meaself_extraction memory)
  - "me-as-llm-fork"    — Claude extracting via dedicated background Agent fork,
                          recall-first protocol. Current me-as-LLM default.
  - "claude-file"       — Claude via ClaudeFileClient (file-queue handoff) — used
                          for backfill stages 4/5+ when LLM_PROVIDER=claude_file

Layout (`v2/data/extraction_provenance.json`):
  {
    "_schema_version": 1,
    "dates": {
       "YYYY-MM-DD": {
         "method": str,
         "model":  str | null,
         "count":  int,
         "last_extracted_at": "ISO8601Z",
         "notes":  str | null,
         "history": [ { same shape minus history } ]
       }
    }
  }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("kvizzing")

_PROV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "extraction_provenance.json"

VALID_METHODS = {"gemini", "me-as-llm-inline", "me-as-llm-fork", "claude-file"}


def _load() -> dict:
    if not _PROV_PATH.exists():
        return {"_schema_version": 1, "dates": {}}
    try:
        return json.loads(_PROV_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("provenance file corrupt; starting fresh: %s", _PROV_PATH)
        return {"_schema_version": 1, "dates": {}}


def _save(doc: dict) -> None:
    _PROV_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROV_PATH.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def record(
    date: str,
    method: str,
    count: int,
    model: str | None = None,
    notes: str | None = None,
    extracted_at: str | None = None,
) -> None:
    """Append a new extraction record for `date`. Prior record moves to history[]."""
    if method not in VALID_METHODS:
        raise ValueError(f"Unknown method {method!r}; valid: {sorted(VALID_METHODS)}")
    doc = _load()
    dates = doc.setdefault("dates", {})
    prior = dates.get(date)
    new_entry = {
        "method": method,
        "model": model,
        "count": count,
        "last_extracted_at": extracted_at or (datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        "notes": notes,
    }
    if prior:
        history = prior.pop("history", [])
        history.append({k: v for k, v in prior.items() if k != "history"})
        new_entry["history"] = history
    else:
        new_entry["history"] = []
    dates[date] = new_entry
    _save(doc)
    log.info("provenance: %s → %s (%d Qs)", date, method, count)


def get(date: str) -> dict | None:
    return _load().get("dates", {}).get(date)


def all_dates() -> dict[str, dict]:
    return _load().get("dates", {})
