export const prerender = false;

export async function load({ fetch }) {
  const decks = await fetch('/data/decks.json').then(r => r.json());
  const gauntletTracker = await fetch('/data/gauntlet_tracker.json').then(r => r.ok ? r.json() : null).catch(() => null);
  return { decks, gauntletTracker };
}
