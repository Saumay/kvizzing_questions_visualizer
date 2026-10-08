import { supabase } from '$lib/supabase';

export interface MemberLink {
  auth_user_id: string;
  username: string;
  is_primary: boolean;
  email: string | null;
  linked_at: string;
}

/** Kicks off the Google OAuth redirect flow. Resolves once the redirect has started. */
export async function signInWithGoogle(redirectPath = '/login') {
  const redirectTo = `${window.location.origin}${redirectPath}`;
  return supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo },
  });
}

/** Email/password signup — no confirmation email required (configured in Supabase). */
export async function signUpWithEmail(email: string, password: string, fullName: string) {
  return supabase.auth.signUp({
    email,
    password,
    options: { data: { full_name: fullName } },
  });
}

export async function signInWithEmail(email: string, password: string) {
  return supabase.auth.signInWithPassword({ email, password });
}

export async function signOut() {
  await supabase.auth.signOut();
}

/** Returns the current Supabase auth session, if any. */
export async function getSession() {
  const { data } = await supabase.auth.getSession();
  return data.session ?? null;
}

/** All member usernames this Google/email account has claimed (possibly several, for the
 *  "same person, multiple historical WhatsApp display names" case). Empty if none yet. */
export async function getMemberLinks(authUserId: string): Promise<MemberLink[]> {
  const { data, error } = await supabase
    .from('member_links')
    .select('*')
    .eq('auth_user_id', authUserId);
  if (error || !data) return [];
  return data as MemberLink[];
}

/**
 * One-time claim: link this account to one or more existing member usernames.
 * `usernames` must include `primaryUsername`. Each username has a UNIQUE
 * constraint across the whole table, so if someone else already claimed one
 * of these, the whole batch fails with a Postgres unique-violation
 * (error.code === '23505') — the caller should re-check availability and retry.
 */
export async function linkMembers(
  authUserId: string,
  usernames: string[],
  primaryUsername: string,
  email: string | null
) {
  const rows = usernames.map(username => ({
    auth_user_id: authUserId,
    username,
    is_primary: username === primaryUsername,
    email,
    linked_at: new Date().toISOString(),
  }));
  return supabase.from('member_links').insert(rows);
}

/** Usernames already claimed by anyone — the picker should exclude these. */
export async function getClaimedUsernames(): Promise<Set<string>> {
  const { data, error } = await supabase.from('claimed_usernames').select('username');
  if (error || !data) return new Set();
  return new Set(data.map((r: { username: string }) => r.username));
}
