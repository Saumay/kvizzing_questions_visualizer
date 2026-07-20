export const prerender = true;

export async function load({ fetch }) {
  const decks = await fetch('/data/decks.json').then(r => r.json());
  return { decks };
}
