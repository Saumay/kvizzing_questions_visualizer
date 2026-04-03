export async function load({ fetch }) {
  const threads = await fetch('/data/rejected_candidates.json')
    .then(r => r.ok ? r.json() : [])
    .catch(() => []);
  return { threads };
}
