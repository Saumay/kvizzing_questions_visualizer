# Optimization backlog

Deferred performance / scale / architecture improvements — things that aren't
worth doing yet but will be once we cross a size or usage threshold. Each
entry captures the problem, the sketch, the trigger (when to revisit), and a
rough effort estimate so future-us can pick it up cold.

Add new entries at the top of "Deferred". Move to "Done" when landed.

## Entry format

```
### <short title>

**Trigger:**   what event / metric makes this worth doing
**Effort:**    S (hours) · M (days) · L (weeks)
**Touches:**   key files / systems

**Problem** — what's the cost of not doing this
**Sketch** — one-paragraph approach
**Alternatives considered** — options ruled out and why
```

---

## Deferred

### Solver=asker fallback on image-burst mini-rounds (me-as-LLM forks)

**Status: half-landed.** Audit check `SOLVER_EQUALS_ASKER` exists (`audit_extraction.py:314-320`) and flags every solver==asker case for manual review. The fork-instructions half of the sketch (explicit "NEVER default to the asker" rule in `extract_loop.py`) is NOT in — checked `instructions_for_ai`, no such rule present. So this is currently caught after the fact, not prevented at extraction time.

**Trigger:** after curator review of 11-06-style poster sessions; if >5% of mini-round Qs end up with solver=asker, address before next bulk run.
**Effort:** S (hours) — just the remaining fork-instructions half
**Touches:** `v2/pipeline/utils/extract_loop.py` (`instructions_for_ai`)

**Problem.** When the fork can't unambiguously pick a winner among rapid-fire image-poster guesses, it defaults to the asker as solver (observed Vats marking himself as solver on Big Lebowski, Gangs of NY, Karate Kid, Munich during 11-06 R2 minimalist posters). Inflates host's solve count, misattributes solves.

**Sketch (remaining).** Add explicit rule to the fork's instructions: "If no clear single solver wins a mini-round item, set answer_solver=null with extraction_confidence=medium. NEVER default to the asker."

**Alternatives considered.** Auto-fix at stage 3 (rewrite solver=asker → null) — too aggressive, asker can legitimately self-solve in some cases (asker guesses for a co-host's Q). Better to keep as audit warning + manual review.

---

### Synthetic timestamps on image-burst mini-rounds (DISC_BEFORE_Q noise)

**Status: not landed.** Checked `extract_loop.py` — no verbatim-timestamp rule in the fork instructions. Audit check `DISC_BEFORE_Q` exists (`audit_extraction.py:242`) so the signal still fires; the fix at the source hasn't shipped.

**Trigger:** when DISC_BEFORE_Q audit issues become >10 per heavy date.
**Effort:** S (hours)
**Touches:** `v2/pipeline/utils/extract_loop.py` (`instructions_for_ai`)

**Problem.** Forks extracting rapid-fire image bursts (poster sessions with 12-28 Qs in 90 min) interpolate timestamps with `:00`/`:30` second markers rather than reading exact message timestamps from input.json. Result: stage 3 flags DISC_BEFORE_Q because synthetic Q timestamp lands after the first reply that arrived seconds earlier. Observed 8 such flags on 2025-11-06 across Vats poster R2 (18:34, 18:58, 19:06).

**Sketch.** Strengthen the fork instructions: "question_timestamp MUST be copied verbatim from the exact input.json message timestamp of the asker's post. Do NOT round, interpolate, or estimate. If unsure which post is the Q in a multi-image burst, pick the earliest matching one."

**Alternatives considered.** Auto-fix at stage 3 (shift Q timestamp to earliest discussion entry) — risky, could mask real chronology bugs. Keep audit signal, fix source.

---

### Dynamic daily-chat loading from R2

**Status: not landed, but `r2_upload.py` reusable.** No "load full day" control on the review page. `v2/pipeline/utils/r2_upload.py` already exists with a working boto3 R2 client (currently used for media images) — its auth/upload boilerplate can be reused for chat blobs, not built from scratch.

**Trigger:** when reviewers start hitting the 40/40 context window on the
review page and want the full day's chat. Also when `rejected_candidates.json`
approaches ~10 MB (see next item — currently 7.5 MB, getting close).
**Effort:** M (2–3 days including R2 upload, frontend fetch, loading UI)
**Touches:** `v2/pipeline/utils/r2_upload.py`, `v2/pipeline/pipeline.py`
(`_write_rejected_candidates` → also emit per-date full-chat blobs),
`v2/visualizer/src/routes/review/+page.svelte` (new "load full day" control).

**Problem.** Today `rejected_candidates.json` ships a fixed 40-before/40-after
slice of chat around each flagged thread, bundled statically. If a reviewer
needs to see earlier or later conversation (a hint that appeared 2 hours
before, a clarification 30 minutes later), the only option is to scroll the
raw `_chat.txt` locally. The bundle already grew from ~1 MB to ~3.7 MB with
40/40 context; it can't scale to "unlimited scroll".

**Sketch.** During `backfill` / `incremental`, parse `_chat.txt` into
per-date JSON blobs (`YYYY-MM-DD.json` = all messages for that day; roughly
1–2K messages, ~300 KB). Upload to a dedicated R2 prefix
(`r2://kvizzing-media/chat/<date>.json` or a separate bucket). The review
page keeps the current 40/40 inline context for instant first paint; a
"Load full day" button fires a `fetch` to the R2 URL and splices the full
day into the visible thread. Signed / timed URLs optional (see privacy
trade-off).

**Alternatives considered.**
- **Supabase table with RLS.** Rejected: raw chat is cold data (rarely
  queried, never mutated), which is the wrong shape for a relational store.
  Per the 2026-04-20 discussion: adding ~170K more rows over the next
  4–5 months would only use ~18 % of the free tier, but Supabase's sweet
  spot is live queries and row-level policies — wasted on flat text. R2 is
  cheaper and more natural.
- **Bundle more context in the static JSON.** Already did the 40/40 bump;
  going higher starts to hurt first-paint on the review page.
- **Query the chat file at runtime.** Requires a backend, which we don't
  have. Netlify Functions / Cloudflare Workers are possible but add a
  moving part.

**Privacy trade-off to resolve at revisit.** R2 public URLs are guessable
(or crawlable if linked). The chat contains real names and private
conversations. Options: (a) accept public-by-obscurity, (b) gate via a
Cloudflare Worker that checks a simple token, (c) sign URLs from a tiny
Supabase edge function. Pick before implementing.

---

### Rejected-candidates JSON pagination

**Status: approaching trigger.** Now 7.5 MB (472 threads), up from 3.7 MB
(246 threads) — tracking almost exactly linear with thread count, faster
than the "+1 MB/quarter" original estimate. At this rate it crosses 10 MB
within the next couple months. Revisit trigger check before then.

**Trigger:** `rejected_candidates.json` > ~10 MB (first-paint / mobile
bandwidth starts to hurt). Currently 7.5 MB with 40/40 context and 472
threads.
**Effort:** S (one afternoon)
**Touches:** `v2/pipeline/utils/export_rejected.py`,
`v2/pipeline/pipeline.py` (the `_write_rejected_candidates` + combine path),
`v2/visualizer/src/routes/review/+page.svelte` and `+page.ts`.

**Problem.** Single monolithic JSON means the review page pays the full
download even when a reviewer only looks at one date. Scales linearly with
archive size.

**Sketch.** Split on write: `rejected_candidates_<YYYY-MM>.json` (monthly
shards) plus a small `rejected_index.json` with thread metadata (id, date,
candidate_count). Review page loads the index eagerly and lazy-fetches the
shard for the month a reviewer opens.

**Alternatives considered.**
- **Per-date shards.** Too fine-grained — 177 fetches for someone browsing
  the full archive. Monthly is ~6 fetches/year.
- **Host on R2 instead of bundling.** Similar idea, extra infra. Revisit if
  combined with the chat-loading work above.

---

## Done

### Questions / sessions JSON pagination — landed 2026-07-26

Shipped a different approach than the original sketch (month-sharding).
Measured where the bytes actually went first: 62% of `questions.json` was
the `discussion` array, and most of that (attempt/chat/confirmation/
elaboration roles) is only ever rendered on the question detail page behind
a click, not in the feed. Month-sharding would've also broken every
full-corpus store method (`random()`, `getAdjacentQuestions()`,
`getAskers()`/`getSolvers()`/`getTopics()` dropdowns) since they scan
`this.questions` regardless of date filter.

Went with index + lazy body instead: `questions.json` now ships each
question with `discussion` trimmed to just `hint`/`answer_reveal` entries
(what the feed card and answer box render inline) plus a `discussion_count`
field for the true total. The full per-question thread lives at
`discussion/<id>.json`, fetched by the question detail page only when there's
more to show than what's already inline. `questions.json`: 10.3 MB → 5.1 MB
(-51%). No store methods changed — the full question set is still eager,
only the heavy field within each object got deferred.

**Touches:** `v2/pipeline/stages/stage6_export.py` (`split_discussion`,
`write_discussion_files`), `v2/visualizer/src/lib/types.ts`,
`v2/visualizer/src/lib/stores/questionStore.ts`,
`v2/visualizer/src/lib/components/QuestionCard.svelte`,
`v2/visualizer/src/routes/question/[id]/+page.svelte`,
`v2/visualizer/src/routes/highlights/+page.svelte`.
