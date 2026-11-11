/**
 * Data files must be available at /data/*.json during dev and build.
 * Easiest setup: run `ln -s ../../data static/data` from the visualizer directory.
 * Or copy the files: cp -r ../data/* static/data/
 */

import { getCachedBulkData, setCachedBulkData } from '$lib/utils/dataCache';

// Was `true`: baked the full questions/sessions/members payload into every
// prerendered page's HTML (28MB+ per page, duplicated per route, growing with
// every new question). Client-fetched once instead and shared across SPA
// navigation, same pattern already used by /question/[id], /session/[id] and
// /member/[username]. See netlify.toml for the matching 200.html redirects.
export const prerender = false;

async function loadBulkData(fetch: typeof window.fetch) {
  // data_version.json is a few bytes and changes only when the pipeline
  // re-exports with different content — cheap to fetch every load so we can
  // tell whether the IndexedDB copy of questions/sessions/members/tags
  // (~28MB combined) is still fresh, and skip re-downloading it if so.
  let version = '';
  try {
    const v = await fetch('/data/data_version.json').then(r => (r.ok ? r.json() : null));
    version = v?.version ?? '';
  } catch {
    version = '';
  }

  if (version) {
    const cached = await getCachedBulkData(version);
    if (cached) return cached;
  }

  const [questions, sessions, members, tags] = await Promise.all([
    fetch('/data/questions.json').then(r => r.json()),
    fetch('/data/sessions.json').then(r => r.json()),
    fetch('/data/members.json').then(r => r.json()),
    fetch('/data/tags.json').then(r => (r.ok ? r.json() : [])).catch(() => []),
  ]);

  if (version) {
    setCachedBulkData({ version, questions, sessions, members, tags });
  }

  return { questions, sessions, members, tags };
}

export async function load({ fetch }) {
  const [bulk, r2Usage, stats] = await Promise.all([
    loadBulkData(fetch),
    fetch('/data/r2_usage.json').then(r => r.ok ? r.json() : null).catch(() => null),
    fetch('/data/stats.json').then(r => r.ok ? r.json() : null).catch(() => null),
  ]);
  const { questions, sessions, members, tags } = bulk;
  return { questions, sessions, members, r2Usage, tags, stats };
}
