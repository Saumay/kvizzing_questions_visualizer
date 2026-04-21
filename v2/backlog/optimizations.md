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

### Dynamic daily-chat loading from R2

**Trigger:** when reviewers start hitting the 40/40 context window on the
review page and want the full day's chat. Also when `rejected_candidates.json`
approaches ~10 MB (see next item).
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

**Trigger:** `rejected_candidates.json` > ~10 MB (first-paint / mobile
bandwidth starts to hurt). Currently 3.7 MB with 40/40 context and 246
threads; roughly tracking +1 MB per quarter of new data.
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

### Questions / sessions JSON pagination

**Trigger:** `questions.json` > ~10 MB (currently monitor; estimate by
`wc -c v2/visualizer/static/data/questions.json`). The visualizer's home
page, question list, and highlights all load this eagerly.
**Effort:** M (touches several store consumers)
**Touches:** `v2/pipeline/stages/stage6_export.py`,
`v2/visualizer/src/lib/stores/questionStore.ts`, most route components.

**Problem.** Same shape as rejected-candidates — a single bundle that every
visitor pays for up-front. Grows ~1 question per row, currently 1326 rows.
At the current capture rate (~300/month) we'll hit 5K rows mid-2027, and
10 MB sometime in 2028.

**Sketch.** Shard by month (likely the most-common filter). Keep
`stats.json`, `sessions.json`, `tags.json`, `members.json` monolithic since
they're aggregates and small. `questionStore` fetches shards on demand based
on the active date filter / route.

**Alternatives considered.**
- **Client-side indexed search (e.g. flexsearch).** Complementary but
  doesn't help first-paint size.
- **Move to Supabase.** Overkill for what's essentially read-only browsing;
  adds a runtime dependency and egress cost.

---

## Done

_(none yet — move entries here as they land, with the commit hash and date)_
