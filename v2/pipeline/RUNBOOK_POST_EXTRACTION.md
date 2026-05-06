# Post-Extraction Runbook

The actual bulk run + everything after, until the archive is shipped.

Prerequisite: every phase in [`RUNBOOK_PRE_EXTRACTION.md`](RUNBOOK_PRE_EXTRACTION.md) passed acceptance.

For routine subcommand usage outside this exercise, see [`RUNNING_GUIDE.md`](RUNNING_GUIDE.md).

---

## Phase 6 — The bulk run

### 6.1 Pre-bulk checklist
- [ ] All pre-extraction phases acceptance criteria met
- [ ] `backups/pre-6mo/` snapshot confirmed
- [ ] `pre-6mo-baseline` tag pushed
- [ ] `GEMINI_API_KEY` active, quota verified (check Google AI Studio dashboard)
- [ ] Network stable
- [ ] Machine on power, sleep disabled
- [ ] No conflicting writes scheduled (e.g. someone else editing chat file or DB)
- [ ] Logs directory writable: `mkdir -p logs`
- [ ] Disk space: at least 2GB free for logs + intermediate outputs

### 6.2 Kick off
Run inside `tmux` or `screen` so it survives terminal disconnects:

```bash
tmux new -s kviz-bulk
cd v2/pipeline
GEMINI_API_KEY=$KEY python3 pipeline.py backfill 2>&1 \
  | tee ../../logs/bulk-6mo-$(date +%Y%m%d-%H%M%S).log
# Detach with Ctrl-b d. Reattach with: tmux attach -t kviz-bulk
```

### 6.3 Monitoring
Every ~30 minutes, glance at the log:
- Process still alive
- Log progressing (not stuck on the same date)
- DB count growing as expected:
  ```bash
  sqlite3 v2/data/questions.db "SELECT date, COUNT(*) FROM questions GROUP BY date ORDER BY date DESC LIMIT 10"
  ```
- No repeated retry loops (sign of API issue or malformed chunk)

### 6.4 Failure handling
- **Process killed / network blip**: re-run `backfill`. Skips already-stored dates via DB lookup. Should pick up where it left off.
- **A specific date errors out**: logged with traceback, pipeline continues to next date. Note the date for Phase 6.6 follow-up.
- **Quota / rate-limit**: built-in retry handles 429s with exponential backoff (10 retries, 13s base sleep). If quota truly exhausted, process eventually errors → wait, resume.
- **JSON parse error from LLM**: logged, retried up to 10x. If exhausted, date marked failed.
- **Pydantic error in stage 3**: that one Q dropped, logged. If many in one date: that date may need reimport with a manual fix to extraction_output.
- **Stage 4 (enrichment) failure**: Q stored without topics; can re-run `pipeline.py reenrich` later.

### 6.5 Mid-run checkpoints
After every ~30 dates processed:
```bash
sqlite3 v2/data/questions.db "
  SELECT date, COUNT(*) AS n FROM questions
  WHERE date >= '<bulk-start-date>'
  GROUP BY date ORDER BY date
" | tee logs/midrun-counts.txt
```
Eyeball: any date with 0 Qs that shouldn't have? Any with 100+ that's suspicious?
Tail log for `WARNING|ERROR`:
```bash
grep -E "WARNING|ERROR|Traceback" logs/bulk-6mo-*.log | tail -50
```

### 6.6 Post-run repair pass
For every date that errored or had suspicious counts:
- Read the log around that date
- If LLM call genuinely failed: re-delete the date and re-run backfill (which will retry)
- If chat parsing issue: investigate stage 1 output

### Phase 6 acceptance
- [ ] All target dates processed (no gaps in `check-coverage`)
- [ ] No unhandled errors in log
- [ ] DB row count consistent with expectations
- [ ] Stage 4 ran for new questions (topics populated; check `SELECT COUNT(*) FROM questions WHERE topic IS NULL`)

---

## Phase 7 — Post-extraction QA

### 7.1 Coverage
```bash
python3 pipeline.py check-coverage
```
Expected: every date in the chat file's range has either a row in DB or a documented reason to skip.

For any flagged date: investigate, possibly re-run.

### 7.2 Quality audits
```bash
python3 pipeline.py audit-quality > logs/qa/audit-quality.txt
python3 pipeline.py audit-missed-sessions > logs/qa/missed-sessions.txt
python3 pipeline.py audit-likely-missed-qs > logs/qa/likely-missed-qs.txt
```

For each audit:
- Compare against baseline from pre-extraction Phase 0.6
- New entries = candidates for the recovery cycle (Phase 8)
- Anything the audits flag should NOT be ignored — at minimum read the headline

### 7.3 Stats sanity
```bash
sqlite3 v2/data/questions.db "
  SELECT date, COUNT(*) FROM questions
  WHERE date BETWEEN '<start>' AND '<end>'
  GROUP BY date ORDER BY date
" | head -50

sqlite3 v2/data/questions.db "
  SELECT asker, COUNT(*) FROM questions
  GROUP BY asker ORDER BY 2 DESC LIMIT 20
"

sqlite3 v2/data/questions.db "
  SELECT topic, COUNT(*) FROM questions
  GROUP BY topic ORDER BY 2 DESC
"

sqlite3 v2/data/questions.db "
  SELECT difficulty, COUNT(*) FROM questions
  GROUP BY difficulty
"
```
Check:
- Daily Q counts roughly consistent with baseline rate
- Top askers match expectations (Pavan, Kartikey, Abhishek, Akshay historically)
- Topic distribution: history / cinema / sports usually top
- Suspicious outlier dates (one date with 100+ Qs, or 0 Qs in a busy week)

### 7.4 Manual spot-check
Pick 30 random Qs from across the bulk run. For each, verify:
- Genuinely a trivia Q (not chat)
- Asker correct
- Solver / answer reasonable
- Discussion thread coherent
- Topics make sense

If <90% pass, **stop**, investigate, possibly re-run problematic dates.

```bash
sqlite3 -json v2/data/questions.db "
  SELECT id, asker, solver, json_extract(payload, '\$.question.text') AS qt,
         json_extract(payload, '\$.answer.text') AS at,
         topic
  FROM questions WHERE date BETWEEN '<start>' AND '<end>'
  ORDER BY RANDOM() LIMIT 30
" | jq
```

### 7.5 Visualizer smoke
```bash
cd v2/visualizer && npm run build
npm run dev
```
In browser:
- `/` (feed): renders, dates load
- `/sessions`: gallery renders, click into a session — Q list correct
- `/highlights`: stats render
- `/review`: rejected threads render with audit signals
- `/question/<id>` for 3 random Qs from the bulk
- Search on `/` works

### Phase 7 acceptance
- [ ] Coverage clean
- [ ] All three audits' delta against baseline understood
- [ ] Stats look sane (no anomalies left unexplained)
- [ ] Spot-check ≥90% pass
- [ ] Visualizer smoke clean

---

## Phase 8 — Recovery cycle (rejected → curator → reimport)

This is the biggest curator-effort phase. Plan for multiple sittings.

### 8.1 AI-assisted triage
```bash
cd v2/pipeline
python3 pipeline.py review-prepare > logs/recovery/review-prepare.log
# Inspect the bundle stats:
python3 -c "
import json; b = json.load(open('../data/review_input.json'));
s = b['stats']; print(s)
"
# AI (Claude in conversation) classifies the unreviewed_threads into
# /tmp/classifications.json, then:
python3 pipeline.py review-finalize --classifications /tmp/classifications.json
```

If unreviewed count is large (~1500+), batch the AI classification across multiple conversations or sittings. After each batch, run `review-finalize` to ship incremental suggestions to the UI.

**Archive the AI classifications for audit trail** (recommended addition to script):
```bash
mkdir -p data/ai_classifications
cp /tmp/classifications.json data/ai_classifications/$(date +%Y%m%d-%H%M%S).json
```

### 8.2 Curator pass
- Curator opens `/review`
- Filters by ✨ AI Missed Q
- For each AI-suggested Missed Q:
  - Read the candidate text + context
  - If genuinely missed → click Missed Q, confirm AI's reason or edit, send
  - If AI was wrong → click Not a Q with appropriate reason
- Note any patterns AI got systematically wrong → log for prompt improvement next cycle

### 8.3 Hand-patch confirmed Missed Qs
For each curator-confirmed Missed Q (filter `/review` by your own Missed Q votes after curator pass):

1. Read the original chat thread + discussion
2. Manually craft an entry in `data/extraction_output/<date>.json`:
   - question_timestamp, question_text, question_asker
   - topics (≥2 to skip stage 4 enrichment)
   - is_session_question, session_quizmaster, session_theme as appropriate
   - answer_text, answer_solver, answer_timestamp
   - discussion array (chronological, with role + is_correct)
   - extraction_confidence ("high" if explicit "yes/correct" exists; else "medium")
3. Re-import:
   ```bash
   python3 pipeline.py reimport <date>
   ```
4. Verify in `/feed?date=<date>` and `/sessions` (if session)
5. Refresh `/review` — the rescued thread should show the ✓ Extracted badge

This is the trains-style recovery, repeated. **Estimated effort: 5–10 minutes per Q × ~90 confirmed Qs ≈ 8–15 hours** spread across multiple sittings.

### 8.4 Re-run audits after recovery
After all confirmed Missed Qs are patched:
```bash
python3 pipeline.py audit-likely-missed-qs
python3 pipeline.py audit-missed-sessions
```
Both should be near-empty. Anything still flagged is "accepted noise" (AI false positives, Dhruv-style historical speculation, etc.).

### Phase 8 acceptance
- [ ] All AI-suggested Missed Qs have a curator decision
- [ ] All curator-confirmed Missed Qs hand-patched into DB
- [ ] Recovery cycle logged for postmortem
- [ ] Audits near-empty post-recovery

---

## Phase 9 — Ancillary enrichment

These can run in any order after Phase 8. None are required for archive correctness; they enrich.

### 9.1 Reactions
If a WhatsApp SQLite backup is available:
```bash
python3 pipeline.py enrich-reactions --db <path-to-wa-msgstore>.db
python3 pipeline.py reimport
```

### 9.2 Media match + R2 upload
```bash
python3 pipeline.py enrich-media --media-dir data/raw/
python3 pipeline.py check-r2
python3 pipeline.py upload-media --media-dir data/raw/
python3 pipeline.py export
```

R2 free tier limits — `check-r2` warns at 80%. If approaching, either upgrade or skip optional media.

### 9.3 Session detection (post-hoc)
```bash
python3 pipeline.py detect-sessions
python3 pipeline.py detect-connect --apply
```

These may overlap with what stage 2's preamble-led rule already caught. Often they find few new things post-bulk-run; that's fine.

### 9.4 Session images
```bash
python3 pipeline.py generate-images
```
Stable Horde, slow but free. Optional.

### 9.5 Final export
```bash
python3 pipeline.py export
```
Refreshes all `static/data/*.json`.

### Phase 9 acceptance
- [ ] Each ancillary subcommand run or explicitly skipped
- [ ] No errors in logs
- [ ] `static/data/` JSON regenerated
- [ ] R2 usage within free-tier bounds

---

## Phase 10 — Acceptance + ship

### 10.1 Final checks
- [ ] All audits clean (or known-noise documented in commit message)
- [ ] DB count = expected (compare to projection from validation phase)
- [ ] No broken JSON in `static/data/`
- [ ] Visualizer build + smoke clean
- [ ] Curator agrees archive is ready

### 10.2 Commit + tag + push
```bash
git status
git add -A   # avoid: review and stage explicitly
git commit -m "data: bulk extraction <YYYY-MM-DD> to <YYYY-MM-DD>"
git tag bulk-$(date +%Y%m%d)
git push origin main --tags
```

### 10.3 Deploy
Netlify auto-deploys on push to main. Wait for build, verify production:
- Production `/` loads
- Production `/review` loads
- Spot-check one new question's URL works

### 10.4 Post-run backup
```bash
mkdir -p backups/post-6mo
cp v2/data/questions.db backups/post-6mo/questions.db.$(date +%Y%m%d)
tar czf backups/post-6mo/full-snapshot-$(date +%Y%m%d).tgz v2/data/
```
Upload `backups/post-6mo/` off-machine (iCloud / S3 / external drive).

### Phase 10 acceptance
- [ ] Tagged + pushed
- [ ] Production deploy verified
- [ ] Post-run backup off-machine

---

## Phase 11 — Postmortem

### 11.1 Capture
For the next cycle, document:
- Patterns curators flagged that LLM still missed → prompt-rule candidates
- Patterns AI mis-classified → AI calibration notes
- Pipeline bugs hit, with cause + fix
- Time per phase, actual vs planned
- Token cost actual vs projected
- What worked, what didn't

Store in: `v2/backlog/postmortem-<date>.md` (per memory: backlog under `v2/`).

### 11.2 Update memory + backlog
- New prompt-rule candidates → `v2/backlog/optimizations.md`
- Tooling gaps → backlog
- Anything non-obvious learned → memory entry (feedback type)

### 11.3 Plan next cycle
Schedule the next 6-month run. Note any pre-work items learned.

### Phase 11 acceptance
- [ ] Postmortem document committed
- [ ] Backlog updated
- [ ] Memory entries (if any) added

---

## Cross-cutting

### Logs
All runs logged to `logs/`. Don't delete during the project. Archive after Phase 11:
```bash
tar czf logs/archive-bulk-<date>.tgz logs/bulk-* logs/recovery/* logs/qa/*
```

### Git state
Don't merge unrelated PRs into main during this exercise. Keep main clean and the rollback story simple.

### If something goes catastrophically wrong
Rollback path:
```bash
# Restore DB
cp backups/pre-6mo/questions.db v2/data/questions.db
# Restore extraction_output
rm -rf v2/data/extraction_output
cp -r backups/pre-6mo/extraction_output v2/data/
# Restore static data
rm -rf v2/visualizer/static/data
cp -r backups/pre-6mo/static-data v2/visualizer/static/data
# Reset to baseline tag
git reset --hard pre-6mo-baseline
```

This puts everything back exactly as it was before Phase 6 started.
