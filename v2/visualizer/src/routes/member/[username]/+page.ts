import { error } from '@sveltejs/kit';

export const prerender = false;

export async function load({ params, parent }) {
  const { members } = await parent();
  const username = decodeURIComponent(params.username);
  const member = members.find((m: { username: string }) => m.username === username);
  if (!member) throw error(404, 'Member not found');
  return { member };
}
