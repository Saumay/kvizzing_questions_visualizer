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

## Done

### Dynamic daily-chat loading from R2 — landed 2026-09-15

Shipped per the sketch, with "public-by-obscurity" chosen for the privacy
trade-off (unguessable `pub-*.r2.dev` URLs, no token/signing — matches the
site's existing posture; revisit only if this stops being acceptable).

`pipeline.py upload-chat` (new command) parses `_chat.txt`, and for every
date that has at least one rejected-candidate thread (checked via the
`attribution_gaps/rejected_candidates/` dir — no point uploading days
nobody will ever ask to expand), uploads that day's full message list to
R2 at `chat/<date>.json` via a new `upload_chat_blobs()` in `r2_upload.py`
(reused `_make_client()`). Writes a small `chat_index.json` manifest
(date → URL) that the review page fetches eagerly (~75 short lines).

Review page (`+page.ts`/`+page.svelte`) keeps the existing 40/40 inline
context for instant first paint; a "Load full day ↓" button appears in the
expanded-context panel only for dates with a manifest entry, fetches the
blob on click (`cache: 'no-store'` — R2's free dev domain can 503 briefly
right after upload), and splices in the full day, marking messages that
match the thread's own candidate timestamps the same way inline context
does.

**Verification note (resolved 2026-10-07):** the click-through fetch was
actually broken, not a browser-automation artifact. The R2 bucket had no
CORS policy, so every cross-origin `fetch()` from the review page (dev or
prod) failed (`Access-Control-Allow-Origin` missing on `GET`, preflight
`OPTIONS` returned 403). `curl` never showed this because CORS is a
browser-only check. Images never hit it either, since `<img src>` doesn't
trigger CORS. Fixed by applying a CORS policy to the `kvizzing-media`
bucket (`GET` from `localhost:5173`, the prod Netlify domain, and its
deploy-preview subdomains) via a one-time `put_bucket_cors` call, using a
new R2 API token scoped to Admin Read & Write (the token already in
`v2/pipeline/.env` only has Object Read & Write and can't touch bucket
settings). Confirmed fixed with a real in-browser `fetch()`: 200, 562
messages for 2025-09-24. No code change needed, the bug was bucket config,
not the fetch logic.

**Touches:** `v2/pipeline/utils/r2_upload.py` (`upload_chat_blobs`),
`v2/pipeline/pipeline.py` (`_run_upload_chat` + `upload-chat` subcommand),
`v2/visualizer/src/routes/review/+page.ts`,
`v2/visualizer/src/routes/review/+page.svelte`.

### Solver=asker fallback rule — landed 2026-09-15

Added the remaining fork-instructions half: `extract_loop.py`'s
`instructions_for_ai` now includes an explicit "NO-WINNER MINI-ROUNDS" rule —
if a rapid-fire image-burst item has no unambiguous single winner, set
`answer_solver=null` with `extraction_confidence=medium`, never default to
the asker. The `SOLVER_EQUALS_ASKER` audit check stays as a backstop.

**Touches:** `v2/pipeline/utils/extract_loop.py` (`instructions_for_ai`)

### Verbatim-timestamp rule — landed 2026-09-15

Added alongside the solver-fallback fix: `instructions_for_ai` now includes
a "VERBATIM TIMESTAMPS" rule — `question_timestamp` must be copied exactly
from the input message's own timestamp, never rounded/interpolated. Should
suppress future `DISC_BEFORE_Q` audit noise from synthetic `:00`/`:30`
timestamps on image-burst mini-rounds.

**Touches:** `v2/pipeline/utils/extract_loop.py` (`instructions_for_ai`)

### Rejected-candidates JSON pagination — landed 2026-09-15

Shipped per the original sketch: `export_rejected()` now writes a
lightweight `rejected_index.json` (id, date, candidate_count, extracted) plus
monthly shard files (`rejected_candidates_<YYYY-MM>.json`) instead of one
monolithic file. The review page (`+page.ts`/`+page.svelte`) loads the index
up front for filtering/sorting/stats and lazy-fetches only the month shards
whose threads actually render — confirmed via network trace that opening a
never-visited month fetches exactly that one shard. The site-wide sidebar
calendar (`+layout.svelte`) also switched from the full body file to the
index, cutting an unnecessary multi-MB fetch on every page load.

`extracted`/`extracted_id` tagging (candidates later promoted into the
archive) moved from a client-side full-corpus cross-reference in `+page.ts`
to server-side in `export_rejected()`, using a new `_extracted_timestamps()`
map (timestamp → question id) — this is what let the index stay lightweight
while still supporting the synthetic self-vote feature, which scans *all*
threads for `extracted`, not just visible ones.

Biggest month shard (Nov 2025) is 4.3 MB — well under the old single-file
7.1 MB and the 10 MB trigger, with headroom before any month alone
approaches it.

**Touches:** `v2/pipeline/utils/export_rejected.py`,
`v2/pipeline/pipeline.py` (`_extracted_timestamps`, `_run_pipeline`,
`_run_export_rejected`), `v2/pipeline/utils/extract_loop.py`,
`v2/pipeline/utils/audit_quality.py` (`audit_rejected_overlap`),
`v2/visualizer/src/routes/review/+page.ts`,
`v2/visualizer/src/routes/review/+page.svelte`,
`v2/visualizer/src/routes/+layout.svelte`, `v2/visualizer/README.md`.

**Gotcha hit during verification:** initial lazy-load implementation used
plain `$state(new Map())`/`$state(new Set())` for the thread-body cache —
Svelte 5's `$state` only makes the *variable* reactive on reassignment,
it does not deep-proxy `.set()`/`.add()` mutations on built-in Map/Set.
Fixed by switching to `SvelteMap`/`SvelteSet` from `svelte/reactivity`.

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
