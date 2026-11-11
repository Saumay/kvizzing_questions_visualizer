export const prerender = false;

export async function load({ fetch }) {
  const decks = await fetch('/data/decks.json').then(r => r.json());
  return { decks };
}
