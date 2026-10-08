export async function load({ fetch }) {
  const [index, questions, autoSuggestionsRaw, chatUrls] = await Promise.all([
    fetch('/data/rejected_index.json').then(r => r.ok ? r.json() : []).catch(() => []),
    fetch('/data/questions.json').then(r => r.ok ? r.json() : []).catch(() => []),
    fetch('/data/auto_review_suggestions.json').then(r => r.ok ? r.json() : null).catch(() => null),
    // date -> full-chat-blob URL on R2, written by `pipeline.py upload-chat`.
    // Tiny (one line per reviewed date) — safe to fetch eagerly.
    fetch('/data/chat_index.json').then(r => r.ok ? r.json() : {}).catch(() => ({})),
  ]);
  // Build a map of question_timestamp → { id, text } for cross-referencing context
  const questionsByTs = new Map<string, { id: string; text: string }>();
  for (const q of questions) {
    if (q.question?.timestamp) {
      questionsByTs.set(q.question.timestamp, { id: q.id, text: q.question.text });
    }
  }
  // Index entries only — id/date/candidate_count/extracted. The heavy
  // candidates/context body is lazy-loaded per month shard by +page.svelte
  // (rejected_candidates_<YYYY-MM>.json) only for threads that render.
  // `extracted` is precomputed server-side by export_rejected() so threads
  // promoted into the archive still show as resolved without needing the
  // full body fetched up front.
  const threads = (index as { id: string; date: string; candidate_count: number; extracted?: boolean }[])
    .filter(t => t.candidate_count > 0);

  // AI suggestions keyed by thread_id (only used when no curator vote exists)
  const suggestionsList = (autoSuggestionsRaw?.suggestions ?? []) as
    { thread_id: string; status: string; reason: string; confidence: number; source: string }[];
  const suggestions = new Map(suggestionsList.map(s => [s.thread_id, s]));

  const chatUrlsByDate = new Map<string, string>(Object.entries(chatUrls ?? {}));

  return { threads, questionsByTs, suggestions, chatUrlsByDate };
}
