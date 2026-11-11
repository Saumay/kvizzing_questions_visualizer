export const prerender = false;

export async function load({ parent }) {
  return await parent();
}
