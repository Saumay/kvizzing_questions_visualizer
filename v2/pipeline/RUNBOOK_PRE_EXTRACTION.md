# Pre-Extraction Runbook

Everything to do **before** running a bulk backfill, so the bulk run is trustworthy.

The matching post-run runbook: [`RUNBOOK_POST_EXTRACTION.md`](RUNBOOK_POST_EXTRACTION.md).
For routine subcommand usage outside this exercise, see [`RUNNING_GUIDE.md`](RUNNING_GUIDE.md).

---

## Goal

When Phase 6 (the actual extraction) starts, we should be confident:

- The prompt is correct and tested.
- The pipeline can resume after failures.
- Backups exist if anything corrupts state.
- Audits and AI-suggest tooling are working.
- We have a known-good baseline to compare the bulk output against.

If any phase fails its acceptance criteria, **stop**, fix, redo. Do not skip ahead.

---

## Phase 0 — Pre-flight

### 0.1 Repo hygiene
```bash
git status                    # clean
git pull origin main
git rev-parse HEAD            # record this commit hash for traceability
cd v2/visualizer && npx svelte-check
cd ../schema && python3 -m pytest test_schema.py
```

### 0.2 Environment & deps
```bash
echo $GEMINI_API_KEY          # must print a key
cat v2/pipeline/.env          # R2_* keys present if media in scope
pip list | grep -E "pydantic|google-genai|requests|imagehash|Pillow"
cd v2/visualizer && npm ci
```

### 0.3 LLM config review
Open `v2/pipeline/config/pipeline_config.json` and confirm:
- `llm_model`: `gemini-2.5-pro`
- `llm_max_tokens`: `65536`
- `llm_max_retries`: `10`
- `llm_rate_limit_sleep_seconds`: `13`
- `chunk_threshold_messages`: `2000`
- `chunk_target_size`: `600`
- `chunk_overlap_messages`: `50`

Then open `v2/pipeline/stages/stage2_extract.py`, search for `_llm_call_once`, verify temperature is set to `0`. If unset (default), add it explicitly. We need determinism for validation.

### 0.4 Inputs sanity
```bash
ls -la v2/pipeline/data/raw/_chat.txt
head -20 v2/pipeline/data/raw/_chat.txt
tail -20 v2/pipeline/data/raw/_chat.txt
```
Confirm chat format unchanged, date range matches expectation.

Smoke parse:
```bash
cd v2/pipeline
python3 -c "
import sys; sys.path.insert(0, '.')
from stages.stage1_parse import run as parse
from utils.config import load_config, load_aliases
from pathlib import Path
config = load_config(Path('config'))
aliases = load_aliases(Path('config'))
chat = open('data/raw/_chat.txt').read()
msgs = parse(chat, aliases, config)
print(f'{len(msgs)} messages parsed')
print('first:', msgs[0])
print('last:', msgs[-1])
"
```

### 0.5 Backups (CRITICAL)
```bash
mkdir -p backups/pre-6mo
cp v2/data/questions.db backups/pre-6mo/
cp -r v2/data/extraction_output backups/pre-6mo/
cp v2/data/pipeline_state.json backups/pre-6mo/ 2>/dev/null || true
cp -r v2/visualizer/static/data backups/pre-6mo/static-data
tar czf backups/pre-6mo/full-snapshot.tgz v2/data/
ls -lah backups/pre-6mo/
```

### 0.6 Baseline audits
```bash
cd v2/pipeline
mkdir -p ../../audits-baseline
python3 pipeline.py audit-quality          > ../../audits-baseline/audit-quality.txt
python3 pipeline.py audit-missed-sessions  > ../../audits-baseline/missed-sessions.txt
python3 pipeline.py audit-likely-missed-qs > ../../audits-baseline/likely-missed-qs.txt
python3 pipeline.py check-coverage         > ../../audits-baseline/coverage.txt
python3 pipeline.py check-r2               > ../../audits-baseline/r2.txt 2>&1 || true
git add audits-baseline && git commit -m "chore: capture baseline audit output before 6-month bulk run"
```

### 0.7 Code freeze
After 0.6, **no more prompt edits, audit edits, or pipeline behaviour changes** until Phase 7 of the post-extraction runbook. Otherwise validation results don't reflect what will actually run.

Document the frozen commit:
```bash
git tag pre-6mo-baseline
git push origin pre-6mo-baseline
```

### Phase 0 acceptance
- [ ] Clean repo, all changes pushed
- [ ] All env vars + deps confirmed
- [ ] LLM config reviewed, temperature=0 set
- [ ] Chat file parses cleanly
- [ ] Backups in `backups/pre-6mo/` totaling expected size
- [ ] Baseline audits committed
- [ ] `pre-6mo-baseline` tag pushed

---

## Phase 1 — Build the diff tool

We need to compare two `extraction_output/<date>.json` files. Without this, "validate the prompt" is just vibes.

### 1.1 Spec
- Input: two paths
- Match key: `(question_timestamp, question_asker)`
- Output: dropped / added / changed / identical sections
- Both human text and machine JSON

### 1.2 Implement
Create `v2/pipeline/utils/diff_extraction.py`. Wire into `pipeline.py` as `diff-extraction --baseline PATH --candidate PATH [--json OUT]`.

### 1.3 Self-test
```bash
python3 pipeline.py diff-extraction \
  --baseline data/extraction_output/2025-10-28.json \
  --candidate data/extraction_output/2025-10-28.json
# should report: identical: N, dropped: 0, added: 0, changed: 0
```

### Phase 1 acceptance
- [ ] Tool exists, self-test passes
- [ ] Committed

---

## Phase 2 — Single-day shakedown

Validate the prompt on one date with known-good output.

### 2.1 Pick the date
**Suggested: `2025-10-28`** — has bonus Q (curator-confirmed valid), session announcement (curator-confirmed not_valid), multiple standalone Qs, casual chat. Recent enough to be representative.

### 2.2 Procedure
```bash
DATE=2025-10-28
mkdir -p backups/shakedown
cp v2/data/extraction_output/$DATE.json backups/shakedown/$DATE.baseline.json
sqlite3 v2/data/questions.db "SELECT id,asker,solver,session_id,payload FROM questions WHERE date='$DATE'" \
  > backups/shakedown/$DATE.db-rows.txt
sqlite3 v2/data/questions.db "DELETE FROM questions WHERE date='$DATE'"
rm v2/data/extraction_output/$DATE.json

cd v2/pipeline
GEMINI_API_KEY=$KEY python3 pipeline.py backfill 2>&1 \
  | tee ../../logs/shakedown-$DATE.log

python3 pipeline.py diff-extraction \
  --baseline ../../backups/shakedown/$DATE.baseline.json \
  --candidate ../data/extraction_output/$DATE.json \
  > ../../backups/shakedown/$DATE.diff.txt
cat ../../backups/shakedown/$DATE.diff.txt
```

### 2.3 Manual review
Open `$DATE.diff.txt`. For every entry:
- **Dropped Q**: real Q? If yes → REGRESSION, stop, investigate.
- **Added Q**: genuine trivia? If no → over-extraction, stop, investigate.
- **Changed Q**: improvement or regression?

### 2.4 Acceptance criteria
- [ ] Zero genuine Qs dropped (recall = 100% on real Qs)
- [ ] All added Qs are genuine (precision = 100% on additions)
- [ ] No Pydantic / JSON parse errors in log
- [ ] Curator-confirmed valid Qs (e.g. `2025-10-28-t4` Bonus) all extracted

### 2.5 If we fail
- Investigate the failing case
- Fix prompt or auto-fix logic
- Restore from `backups/shakedown/$DATE.baseline.json` to DB if needed:
  ```bash
  cp backups/shakedown/$DATE.baseline.json v2/data/extraction_output/$DATE.json
  python3 pipeline.py reimport $DATE
  ```
- Re-run shakedown
- Don't move past Phase 2 until acceptance is met

---

## Phase 3 — Multi-day validation

Single date can hide pattern-specific issues. Validate 7 dates with deliberate variety.

### 3.1 Date selection
Pick 7 dates covering:
- A formal session (numbered Qs)
- An informal session (Pavan railways `2025-11-03` or photos `2025-11-05`)
- A connect quiz
- An image-heavy day
- A casual-chat-heavy day with few Qs
- An old date (early in archive — chat format drift check)
- A timezone-edge day (UTC midnight crossing IST 5:30am)

### 3.2 Procedure
For each date: same as Phase 2 (snapshot, wipe, re-run, diff, manual review).

```bash
for DATE in 2025-DD-DD 2025-DD-DD ...; do
  cp v2/data/extraction_output/$DATE.json backups/validation/$DATE.baseline.json
  sqlite3 v2/data/questions.db "DELETE FROM questions WHERE date='$DATE'"
  rm v2/data/extraction_output/$DATE.json
done

# Single backfill processes all wiped dates
GEMINI_API_KEY=$KEY python3 pipeline.py backfill | tee logs/validation.log

for DATE in ...; do
  python3 pipeline.py diff-extraction \
    --baseline backups/validation/$DATE.baseline.json \
    --candidate v2/data/extraction_output/$DATE.json \
    > backups/validation/$DATE.diff.txt
done
```

### 3.3 Aggregate scoring
Across 7 dates:
- Total Qs in baseline vs new
- Recall (Qs preserved): target ≥98%
- Precision (added Qs that are genuine): target ≥95%
- Pattern check: did the new STRONG-signals rule catch standalone Q-prefix / long-setup Qs that were previously missed? Sample one example, prove it.

### 3.4 Determinism check
Re-run one of the 7 dates a second time (wipe + backfill again). Diff the two runs. Measure non-determinism. If significant (>1% of Qs differ), investigate temperature setting; pin to 0 and re-test.

### 3.5 Restore
After validation, restore the DB rows for these 7 dates:
```bash
for DATE in ...; do
  python3 pipeline.py reimport $DATE
done
```

### Phase 3 acceptance
- [ ] All 7 diffs reviewed manually
- [ ] Recall ≥98%, precision ≥95%
- [ ] STRONG-signals rule proven to catch a previously-missed Q
- [ ] Determinism check passed (or temp=0 re-tested)
- [ ] DB restored to baseline state

---

## Phase 4 — Audit + AI-suggest dry run

Verify the post-extraction tooling chain works on validation data.

### 4.1 Address audit gaps from prior review
Before bulk:
- **Audit filtering** (gap #1, #3): `audit-likely-missed-qs` should skip already-extracted threads (DB cross-ref). Add an `--include-resolved` escape hatch.
- **Audit regex expansion** (gap #12): add `Connect:`, `Identify`, `ID this/the`, `Name (this|the)` prefixes.
- **`audit-missed-sessions`**: also benefits from extracted-thread filter.

Commit these tooling fixes; they ARE part of the frozen baseline (different from the prompt code freeze).

### 4.2 Exercise audits on validation data
```bash
python3 pipeline.py audit-missed-sessions --date 2025-11-03
python3 pipeline.py audit-likely-missed-qs --date 2025-11-03
python3 pipeline.py audit-quality
```

Confirm signal-to-noise improved after 4.1 changes.

### 4.3 review-prepare → AI classify → review-finalize on validation set
```bash
python3 pipeline.py review-prepare --date 2025-10-28
# AI (Claude in conversation) reads bundle, classifies, writes /tmp/classifications.json
python3 pipeline.py review-finalize --classifications /tmp/classifications.json
```

### 4.4 End-to-end UI test
- Open `/review`
- Confirm AI badges render with reason text
- Confirm "AI N" filter chip works
- Click an AI suggestion's matching status button → reason picker pre-fills with AI's reason → submit
- Confirm Supabase write succeeded (check network tab)
- Refresh page, confirm badge swapped from ✨ AI to real-vote display
- Confirm leaderboard still shows correct count

### Phase 4 acceptance
- [ ] Audit gaps fixed and committed
- [ ] All three audits return only signal
- [ ] AI suggestions render correctly with reasons
- [ ] Confirm flow works end-to-end without errors

---

## Phase 5 — End-to-end 1-week dry run

Full pipeline on 1 week of data (different week than Phase 3 dates) to test scale, time, cost, and the full ancillary chain.

### 5.1 Select a week
A continuous 7-day stretch with mixed activity. Avoid the dates we used in Phase 3 (already validated) and Phase 2 (already validated). Suggested: an older week or a week we haven't deeply touched yet.

### 5.2 Procedure
```bash
WEEK_START=2025-MM-DD
WEEK_END=2025-MM-DD

# Snapshot
mkdir -p backups/dryrun-week
sqlite3 v2/data/questions.db ".backup backups/dryrun-week/questions.db"
for DATE in $(seq dates from WEEK_START to WEEK_END); do
  cp v2/data/extraction_output/$DATE.json backups/dryrun-week/ 2>/dev/null
done

# Wipe
sqlite3 v2/data/questions.db "DELETE FROM questions WHERE date BETWEEN '$WEEK_START' AND '$WEEK_END'"
rm v2/data/extraction_output/$WEEK_START.json … (or loop)

# Run
GEMINI_API_KEY=$KEY python3 pipeline.py backfill 2>&1 | tee logs/dryrun-week.log

# Ancillaries
python3 pipeline.py enrich-media --media-dir data/raw/   # if media available
# python3 pipeline.py upload-media --media-dir data/raw/  # if R2 in scope
python3 pipeline.py detect-sessions
python3 pipeline.py detect-connect
# python3 pipeline.py enrich-reactions --db <wa-backup>   # if available
python3 pipeline.py generate-images                       # optional, slow

# Audits
python3 pipeline.py audit-quality
python3 pipeline.py audit-missed-sessions
python3 pipeline.py audit-likely-missed-qs

# AI suggest
python3 pipeline.py review-prepare
# AI classify in conversation
python3 pipeline.py review-finalize --classifications /tmp/classifications.json

# Visualizer smoke
cd v2/visualizer && npm run build && npm run dev
# click through /, /sessions, /highlights, /review, /question/<id>
```

### 5.3 Capture metrics
- Wall time per date (avg, p50, p95)
- Total tokens used
- Errors / retries
- Memory usage (peak)
- Disk used

### 5.4 Extrapolate to 6 months
- ~180 dates × per-date wall time = total bulk run estimate
- × per-date tokens = total cost
- Decide: overnight run feasible? Need to pause for quota?

### 5.5 Restore
After dry run, restore the week:
```bash
for DATE in ...; do
  cp backups/dryrun-week/$DATE.json v2/data/extraction_output/
  python3 pipeline.py reimport $DATE
done
```
OR if it makes more sense: keep the dry-run output if it validated against the baseline cleanly (one less date to re-run during bulk).

### Phase 5 acceptance
- [ ] Pipeline ran end-to-end without manual intervention
- [ ] Time + token metrics recorded
- [ ] Visualizer smoke passes
- [ ] Audits all clean
- [ ] Cost projection for 6mo within budget
- [ ] Failure modes encountered (if any) documented

---

## Pre-extraction final checklist

Before kicking off Phase 6 (the actual bulk run), confirm:

- [ ] Phase 0 — backups exist, code frozen, baseline tagged
- [ ] Phase 1 — diff tool committed and working
- [ ] Phase 2 — 1-day shakedown passed acceptance
- [ ] Phase 3 — 7-day validation passed acceptance, recall ≥98%
- [ ] Phase 4 — audits + AI-suggest tooling proven on validation data
- [ ] Phase 5 — 1-week E2E dry run completed, metrics captured
- [ ] Cost projection within budget
- [ ] Time projection compatible with availability (likely overnight + curator follow-up)
- [ ] No conflicting writes scheduled during bulk run
- [ ] Network stable, machine on power
- [ ] Curator (Saumay, Smy) availability for Phase 8 confirmed

When all boxes are checked, proceed to [`RUNBOOK_POST_EXTRACTION.md`](RUNBOOK_POST_EXTRACTION.md), Phase 6.
