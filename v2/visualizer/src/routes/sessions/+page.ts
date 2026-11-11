export const prerender = false;

export async function load({ parent }) {
  const data = await parent();
  return { sessions: data.sessions, questions: data.questions };
}
