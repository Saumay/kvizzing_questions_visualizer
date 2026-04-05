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
  // Filter out malformed entries and threads where any candidate was already extracted
  const filteredThreads = threads.filter((t: any) =>
    t.candidates?.length > 0 &&
    !t.candidates.some((c: any) => questionsByTs.has(c.timestamp))
  );
  return { threads: filteredThreads, questionsByTs };
}
