/**
 * Data files must be available at /data/*.json during dev and build.
 * Easiest setup: run `ln -s ../../data static/data` from the visualizer directory.
 * Or copy the files: cp -r ../data/* static/data/
 */

// Was `true`: baked the full questions/sessions/members payload into every
// prerendered page's HTML (28MB+ per page, duplicated per route, growing with
// every new question). Client-fetched once instead and shared across SPA
// navigation, same pattern already used by /question/[id], /session/[id] and
// /member/[username]. See netlify.toml for the matching 200.html redirects.
export const prerender = false;

export async function load({ fetch }) {
  const [questions, sessions, members, r2Usage, tags, stats] = await Promise.all([
    fetch('/data/questions.json').then(r => r.json()),
    fetch('/data/sessions.json').then(r => r.json()),
    fetch('/data/members.json').then(r => r.json()),
    fetch('/data/r2_usage.json').then(r => r.ok ? r.json() : null).catch(() => null),
    fetch('/data/tags.json').then(r => r.ok ? r.json() : []).catch(() => []),
    fetch('/data/stats.json').then(r => r.ok ? r.json() : null).catch(() => null),
  ]);
  return { questions, sessions, members, r2Usage, tags, stats };
}
