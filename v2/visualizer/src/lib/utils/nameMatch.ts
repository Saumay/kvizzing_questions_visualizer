import Fuse from 'fuse.js';
import type { Member } from '$lib/types';

/**
 * Given a person's real name (from their Google account, or typed at email
 * signup) and the full member list, returns the members most likely to be
 * the same person — for a "select which of these are you" picker rather
 * than making someone scroll an alphabetical list of 75 names.
 */
export function suggestMembers(fullName: string, members: Member[], limit = 8): Member[] {
  const name = fullName.trim();
  if (!name) return [];

  const fuse = new Fuse(members, {
    keys: ['display_name', 'username'],
    threshold: 0.45,
    ignoreLocation: true,
  });

  // Match on the full name, and on each individual word (handles "Saumay Khandelwal"
  // matching a WhatsApp display name that's just "Saumay" or just "Khandelwal").
  const queries = [name, ...name.split(/\s+/).filter(w => w.length > 1)];
  const seen = new Map<string, number>(); // username -> best (lowest) score
  for (const q of queries) {
    for (const r of fuse.search(q)) {
      const prev = seen.get(r.item.username);
      const score = r.score ?? 1;
      if (prev === undefined || score < prev) seen.set(r.item.username, score);
    }
  }

  return [...seen.entries()]
    .sort((a, b) => a[1] - b[1])
    .slice(0, limit)
    .map(([username]) => members.find(m => m.username === username)!)
    .filter(Boolean);
}
