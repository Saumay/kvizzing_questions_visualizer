import Fuse from 'fuse.js';
import type { Member } from '$lib/types';

/**
 * Given a person's real name (from their Google account, or typed at email
 * signup) and the full member list, returns the members most likely to be
 * the same person, for a "select which of these are you" picker rather
 * than making someone scroll an alphabetical list of 75 names.
 */
// Above this score (0 = exact match, 1 = no similarity), a result is noise:
// a short per-word query (e.g. "Check" out of "Test Signup Check") can still
// fuzzy-match an unrelated longer name by sheer coincidental character
// overlap once minMatchCharLength lets it through. Found via a real signup
// of "Test Signup Check", which without this cutoff (and without
// includeScore - see below) surfaced totally unrelated members like
// "Abhishek Vats" and "KVIZ SHeik" as top suggestions.
const MAX_SUGGESTION_SCORE = 0.35;

export function suggestMembers(fullName: string, members: Member[], limit = 8): Member[] {
  const name = fullName.trim();
  if (!name) return [];

  const fuse = new Fuse(members, {
    keys: ['display_name', 'username'],
    threshold: 0.4,
    // Without this, "Check" can match 3-4 scattered characters deep inside
    // an unrelated longer name (e.g. "Abhishek"); requiring a longer
    // matched run filters that out while still allowing real short names
    // ("Vats", "Dhruv") to match in full.
    minMatchCharLength: 4,
    ignoreLocation: true,
    // Required for the "best (lowest) score" dedup below to do anything:
    // without it, r.score is always undefined, every candidate falls back
    // to score 1, and the sort-by-score step becomes a no-op - the first
    // (arbitrary) match per query wins instead of the best one.
    includeScore: true,
  });

  // Match on the full name, and on each individual word (handles "Saumay Khandelwal"
  // matching a WhatsApp display name that's just "Saumay" or just "Khandelwal").
  const queries = [name, ...name.split(/\s+/).filter(w => w.length > 1)];
  const seen = new Map<string, number>(); // username -> best (lowest) score
  for (const q of queries) {
    for (const r of fuse.search(q)) {
      const score = r.score ?? 1;
      if (score > MAX_SUGGESTION_SCORE) continue;
      const prev = seen.get(r.item.username);
      if (prev === undefined || score < prev) seen.set(r.item.username, score);
    }
  }

  return [...seen.entries()]
    .sort((a, b) => a[1] - b[1])
    .slice(0, limit)
    .map(([username]) => members.find(m => m.username === username)!)
    .filter(Boolean);
}
