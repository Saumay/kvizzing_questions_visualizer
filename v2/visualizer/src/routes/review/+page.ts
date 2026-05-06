export async function load({ fetch }) {
  const [threads, questions] = await Promise.all([
    fetch('/data/rejected_candidates.json').then(r => r.ok ? r.json() : []).catch(() => []),
    fetch('/data/questions.json').then(r => r.ok ? r.json() : []).catch(() => []),
  ]);
  // Build a map of question_timestamp → { id, text } for cross-referencing context
  const questionsByTs = new Map<string, { id: string; text: string }>();
  for (const q of questions) {
    if (q.question?.timestamp) {
      questionsByTs.set(q.question.timestamp, { id: q.id, text: q.question.text });
    }
  }
  // Keep all non-empty threads. Tag candidates and the thread when their
  // timestamp now exists in the extracted DB — UI shows them as resolved
  // instead of hiding the row.
  const filteredThreads = threads
    .filter((t: any) => t.candidates?.length > 0)
    .map((t: any) => {
      const cands = t.candidates.map((c: any) => {
        const q = questionsByTs.get(c.timestamp);
        return q ? { ...c, extracted_id: q.id } : c;
      });
      const extracted = cands.some((c: any) => c.extracted_id);
      return { ...t, candidates: cands, extracted };
    });
  return { threads: filteredThreads, questionsByTs };
}
