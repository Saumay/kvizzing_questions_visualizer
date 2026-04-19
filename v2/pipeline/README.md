# KVizzing Pipeline

Python pipeline for extracting, structuring, enriching, and exporting trivia Q&A pairs from WhatsApp chat exports.

## Architecture

```
WhatsApp _chat.txt
  │
  ├─ Stage 0 — Filter         Date selection, backfill gap detection
  ├─ Stage 1 — Parse           Raw text → structured messages
  ├─ Stage 2 — Extract         LLM-based Q&A extraction (Gemini)
  ├─ Stage 3 — Structure       Raw dicts → Pydantic models, ID generation, stats
  ├─ Stage 4 — Enrich          LLM topic categorisation (23 categories)
  ├─ Stage 5 — Store           SQLite upsert with enrichment preservation
  └─ Stage 6 — Export          JSON files for the visualizer
                │
                ├─ questions.json      Full question archive
                ├─ sessions.json       Session index with scores
                ├─ stats.json          Aggregated statistics
                ├─ tags.json           Tag frequency index
                └─ members.json        Member profiles + stats
```

Post-pipeline steps (run automatically during backfill):
- **Media matching** — Timestamp-based WhatsApp media file → question matching
- **R2 upload** — Upload matched media to Cloudflare R2 CDN
- **Session images** — AI-generated backgrounds via Stable Horde
- **Rejected candidates** — Export flagged-but-rejected candidates for community review

## Quick Start

```bash
# Install dependencies
pip install pydantic google-genai boto3 requests imagehash Pillow

# First-time extraction (requires LLM API key)
GEMINI_API_KEY=xxx python3 pipeline.py backfill

# Routine update
GEMINI_API_KEY=xxx python3 pipeline.py incremental

# Re-export without LLM
python3 pipeline.py export
```

## Commands

| Command | Description |
|---|---|
| `backfill` | Process all unextracted dates (full pipeline per date) |
| `incremental` | Process dates after the last stored date |
| `export` | Re-generate JSON from DB (no LLM) |
| `reimport [DATES]` | Re-import extraction files with auto-fixes (stages 3-6) |
| `reenrich [--all]` | LLM topic re-enrichment |
| `enrich-media --media-dir PATH` | Match media files to questions |
| `upload-media --media-dir PATH` | Upload media to R2 |
| `generate-images` | Generate session background images |
| `audit-quality` | Check for non-questions, low quality, rejected overlaps |
| `check-r2` | R2 free-tier usage report |
| `check-coverage` | Find missed dates or low extraction counts |
| `export-rejected` | Export rejected candidates to JSON |
| `detect-sessions` | Post-hoc session detection in extraction files |
| `cleanup-r2` | Delete unreferenced R2 objects |

See [RUNNING_GUIDE.md](RUNNING_GUIDE.md) for detailed usage, workflows, and configuration.

## Key Design Decisions

- **Extraction cache** — `data/extraction_output/YYYY-MM-DD.json` files cache LLM results. If a file exists, the LLM is skipped. Manual edits to these files always win.
- **Enrichment preservation** — Stage 5 upsert never overwrites richer data (topics, tags, media) with poorer re-extraction data.
- **Self-healing extraction** — 14-type auto-fix system + targeted LLM micro-calls for ambiguous confirmations.
- **Per-date processing** — Each date is fully processed (extract → store → media → export) before the next, ensuring partial progress is preserved on failures.
- **Transient error retry** — Timeouts, connection errors, and 503s retry with 30s minimum delay.

## Directory Structure

```
pipeline.py                  # Main orchestrator
stages/                      # Pipeline stages 0-6
clients/llm.py               # LLM provider (Gemini)
utils/
  audit_extraction.py        # Auto-fix engine (14 fix types)
  audit_quality.py           # Post-export quality checks
  media_match.py             # Timestamp-based media matching with perceptual dedup
  r2_upload.py               # Cloudflare R2 upload
  generate_session_images.py # Stable Horde image generation
  detect_sessions.py         # Post-hoc session detector
  detect_connect_quizzes.py  # LLM connect quiz classifier
  export_rejected.py         # Rejected candidate export
  config.py                  # Topic loading, aliases
  log_setup.py               # Logging configuration
config/
  pipeline_config.json       # Pipeline parameters
  topics.json                # 23 topic categories (single source of truth)
  members.json               # Member display names & avatars
  session_overrides.json     # Manual session corrections
  username_aliases.json      # Username canonicalization
.env                         # R2 + LLM credentials (gitignored)
```

## LLM Provider

| Provider | Enable with | Notes |
|---|---|---|
| Gemini | `GEMINI_API_KEY` | Free tier, 1M context (gemini-2.5-pro) |
