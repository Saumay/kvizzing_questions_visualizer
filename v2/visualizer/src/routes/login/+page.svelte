<script lang="ts">
  import { getContext, onMount } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { supabase } from '$lib/supabase';
  import {
    signInWithGoogle, signUpWithEmail, signInWithEmail, signOut,
    getMemberLinks, linkMembers, getClaimedUsernames,
  } from '$lib/auth';
  import { suggestMembers } from '$lib/utils/nameMatch';

  const store = getContext<QuestionStore>('store');
  const allMembers = store.getMembers().slice().sort((a, b) => a.display_name.localeCompare(b.display_name));

  type Stage = 'loading' | 'signed_out' | 'picking_member' | 'linked' | 'error';
  let stage = $state<Stage>('loading');
  let errorMessage = $state('');

  // ── Email/password form state ──
  let emailMode = $state<'signin' | 'signup'>('signin');
  let emailInput = $state('');
  let passwordInput = $state('');
  let nameInput = $state(''); // used only for signup, to seed suggestions
  let submittingEmail = $state(false);

  // ── Session / member-linking state ──
  let authUserId = $state('');
  let accountEmail = $state('');
  let accountName = $state('');
  let claimedUsernames = $state<Set<string>>(new Set());
  let selected = $state<Set<string>>(new Set());
  let customNames = $state<Set<string>>(new Set()); // added via "can't find your name" fallback
  let customNameInput = $state('');
  let primary = $state('');
  let memberSearch = $state('');
  let saving = $state(false);

  const suggested = $derived(
    accountName ? suggestMembers(accountName, allMembers.filter(m => !claimedUsernames.has(m.username))) : []
  );
  const availableMembers = $derived(allMembers.filter(m => !claimedUsernames.has(m.username)));
  const searchResults = $derived(
    memberSearch.trim()
      ? availableMembers.filter(m => m.display_name.toLowerCase().includes(memberSearch.trim().toLowerCase()))
      : availableMembers
  );
  const selectedList = $derived([...selected]);

  // TEMPORARY: preview the "pick your member(s)" screen without finishing Google/email
  // setup. Visit /login?preview=1. Writes nothing to Supabase. Remove once real
  // sign-in is fully working end to end.
  const isPreview = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('preview') === '1';

  async function refresh() {
    if (isPreview) {
      authUserId = 'preview';
      accountEmail = 'preview@example.com';
      accountName = 'Preview Person';
      claimedUsernames = await getClaimedUsernames().catch(() => new Set<string>());
      stage = 'picking_member';
      return;
    }

    const { data, error } = await supabase.auth.getSession();
    if (error) { stage = 'error'; errorMessage = error.message; return; }
    const session = data.session;
    if (!session) { stage = 'signed_out'; return; }

    authUserId = session.user.id;
    accountEmail = session.user.email ?? '';
    accountName = (session.user.user_metadata?.full_name as string) || (session.user.user_metadata?.name as string) || '';

    const links = await getMemberLinks(authUserId);
    if (links.length > 0) {
      const primaryLink = links.find(l => l.is_primary) ?? links[0];
      applyIdentity(primaryLink.username);
      return;
    }

    claimedUsernames = await getClaimedUsernames();
    stage = 'picking_member';
  }

  function applyIdentity(username: string) {
    localStorage.setItem('kvizzing-reviewer-name', username);
    localStorage.setItem('kvizzing_google_linked', 'true');
    stage = 'linked';
    // Full reload so +layout.svelte's session/identity-loading logic re-runs cleanly.
    setTimeout(() => { window.location.href = '/'; }, 600);
  }

  function toggleSelect(username: string) {
    const next = new Set(selected);
    if (next.has(username)) {
      next.delete(username);
      if (primary === username) primary = [...next][0] ?? '';
    } else {
      next.add(username);
      if (!primary) primary = username;
    }
    selected = next;
  }

  function addCustomName() {
    const name = customNameInput.trim();
    if (!name || claimedUsernames.has(name)) return;
    customNames = new Set([...customNames, name]);
    customNameInput = '';
    toggleSelect(name);
  }

  function removeCustomName(name: string) {
    const next = new Set(customNames);
    next.delete(name);
    customNames = next;
    if (selected.has(name)) toggleSelect(name);
  }

  async function confirmMembers() {
    if (selected.size === 0 || !primary || !authUserId) return;
    if (isPreview) { applyIdentity(primary); return; }
    saving = true;
    const { error } = await linkMembers(authUserId, [...selected], primary, accountEmail || null);
    saving = false;
    if (error) {
      if (error.code === '23505') {
        errorMessage = 'Someone just claimed one of those names — recheck your picks.';
        claimedUsernames = await getClaimedUsernames();
        selected = new Set([...selected].filter(u => !claimedUsernames.has(u)));
        if (!selected.has(primary)) primary = [...selected][0] ?? '';
      } else {
        stage = 'error'; errorMessage = error.message;
      }
      return;
    }
    applyIdentity(primary);
  }

  async function onGoogleClick() {
    errorMessage = '';
    const { error } = await signInWithGoogle('/login');
    if (error) { stage = 'error'; errorMessage = error.message; }
  }

  async function submitEmailForm() {
    errorMessage = '';
    if (!emailInput.trim() || !passwordInput) return;
    submittingEmail = true;
    if (emailMode === 'signup') {
      const { error } = await signUpWithEmail(emailInput.trim(), passwordInput, nameInput.trim());
      submittingEmail = false;
      if (error) { errorMessage = error.message; return; }
    } else {
      const { error } = await signInWithEmail(emailInput.trim(), passwordInput);
      submittingEmail = false;
      if (error) { errorMessage = error.message; return; }
    }
    stage = 'loading';
    refresh();
  }

  async function switchAccount() {
    await signOut();
    localStorage.removeItem('kvizzing_google_linked');
    stage = 'signed_out';
  }

  onMount(refresh);
</script>

<svelte:head>
  <title>Log in · KVizzing</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center bg-ui-parchment px-4 py-8">
  <div class="w-full max-w-sm bg-ui-card border border-stone-200/80 dark:border-zinc-600/80 rounded-2xl shadow-sm p-6">
    <div class="flex items-center gap-3 mb-6">
      <div class="w-10 h-10 rounded-xl bg-primary-500 flex items-center justify-center text-white font-bold text-lg shadow">KV</div>
      <div>
        <h1 class="font-bold text-gray-900 dark:text-white text-lg leading-tight">KVizzing</h1>
        <p class="text-xs text-gray-400">Sign in to enter</p>
      </div>
    </div>

    {#if stage === 'loading'}
      <div class="flex items-center gap-2 text-gray-400 text-sm py-6 justify-center">
        <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        Checking session…
      </div>

    {:else if stage === 'signed_out'}
      <button
        onclick={onGoogleClick}
        class="w-full flex items-center justify-center gap-2.5 border border-gray-300 dark:border-gray-600 rounded-lg py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
      >
        <svg class="w-4 h-4" viewBox="0 0 24 24">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
        </svg>
        Sign in with Google
      </button>

      <div class="flex items-center gap-2 my-4">
        <div class="flex-1 h-px bg-gray-200 dark:bg-gray-700"></div>
        <span class="text-[11px] text-gray-400">or with email</span>
        <div class="flex-1 h-px bg-gray-200 dark:bg-gray-700"></div>
      </div>

      <div class="flex gap-1 mb-3 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
        <button
          onclick={() => emailMode = 'signin'}
          class="flex-1 py-1.5 rounded-md text-xs font-medium transition-colors {emailMode === 'signin' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500'}"
        >Log in</button>
        <button
          onclick={() => emailMode = 'signup'}
          class="flex-1 py-1.5 rounded-md text-xs font-medium transition-colors {emailMode === 'signup' ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500'}"
        >Sign up</button>
      </div>

      <form onsubmit={(e) => { e.preventDefault(); submitEmailForm(); }} class="space-y-2">
        {#if emailMode === 'signup'}
          <input
            type="text" placeholder="Your name" bind:value={nameInput}
            class="w-full text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
          />
        {/if}
        <input
          type="email" placeholder="Email" bind:value={emailInput} required
          class="w-full text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
        />
        <input
          type="password" placeholder="Password" bind:value={passwordInput} required minlength="6"
          class="w-full text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
        />
        <button
          type="submit"
          disabled={submittingEmail || !emailInput.trim() || !passwordInput}
          class="w-full py-2.5 rounded-lg text-sm font-medium text-white bg-primary-500 hover:bg-primary-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >{submittingEmail ? 'Please wait…' : emailMode === 'signup' ? 'Create account' : 'Log in'}</button>
      </form>

      {#if errorMessage}
        <p class="mt-3 text-xs text-red-500">{errorMessage}</p>
      {/if}
      <p class="mt-4 text-[11px] text-gray-400 text-center">Used only to identify you as a group member.</p>

    {:else if stage === 'picking_member'}
      <p class="text-sm text-gray-700 dark:text-gray-300 mb-1">Signed in as <span class="font-medium">{accountEmail || accountName}</span>.</p>
      <p class="text-xs text-gray-400 mb-3">
        Select every name in the chat history that's <span class="font-medium">you</span> — some people show up under more than one (renamed, or WhatsApp's stylised fonts split into different names). One-time, locked to your account once confirmed.
      </p>

      {#if suggested.length > 0}
        <p class="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Suggested for you</p>
        <div class="flex flex-wrap gap-1.5 mb-4">
          {#each suggested as m}
            <button
              onclick={() => toggleSelect(m.username)}
              class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium border transition-colors {selected.has(m.username)
                ? 'bg-primary-500 border-primary-500 text-white'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:border-primary-300'}"
            >
              {#if selected.has(m.username)}
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" /></svg>
              {/if}
              {m.display_name}
            </button>
          {/each}
        </div>
      {/if}

      <p class="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">All members</p>
      <input
        type="text" placeholder="Search names…" bind:value={memberSearch}
        class="w-full text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 mb-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
      />
      <div class="max-h-40 overflow-y-auto border border-gray-100 dark:border-gray-700 rounded-lg mb-4 divide-y divide-gray-50 dark:divide-gray-800">
        {#each searchResults as m}
          <button
            onclick={() => toggleSelect(m.username)}
            class="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors {selected.has(m.username) ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400' : 'text-gray-700 dark:text-gray-300'}"
          >
            <span class="w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center {selected.has(m.username) ? 'bg-primary-500 border-primary-500' : 'border-gray-300 dark:border-gray-600'}">
              {#if selected.has(m.username)}
                <svg class="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" /></svg>
              {/if}
            </span>
            {m.display_name}
          </button>
        {:else}
          <p class="px-3 py-3 text-xs text-gray-400 text-center">No matches</p>
        {/each}
      </div>

      <details class="mb-4 group">
        <summary class="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-pointer select-none">
          Can't find your name? You may never have asked or answered a question in the archive — add it
        </summary>
        <div class="flex gap-2 mt-2">
          <input
            type="text" placeholder="Type your name exactly as it'd appear" bind:value={customNameInput}
            onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomName(); } }}
            class="flex-1 text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
          />
          <button
            onclick={addCustomName}
            disabled={!customNameInput.trim() || claimedUsernames.has(customNameInput.trim())}
            class="px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-primary-500 hover:bg-primary-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >Add</button>
        </div>
        {#if customNameInput.trim() && claimedUsernames.has(customNameInput.trim())}
          <p class="text-[11px] text-red-500 mt-1">That name's already claimed by someone else.</p>
        {/if}
      </details>

      {#if selectedList.length > 0}
        <p class="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
          Picked ({selectedList.length}) — which is your main one?
        </p>
        <div class="space-y-1 mb-4">
          {#each selectedList as u}
            {@const m = allMembers.find(mm => mm.username === u)}
            <label class="flex items-center gap-2 px-2 py-1 rounded-lg cursor-pointer {primary === u ? 'bg-primary-50 dark:bg-primary-900/20' : ''}">
              <input type="radio" name="primary" checked={primary === u} onchange={() => primary = u} class="accent-primary-500" />
              <span class="text-sm text-gray-700 dark:text-gray-200">{m?.display_name ?? u}</span>
              {#if !m}<span class="text-[10px] text-gray-400">(new)</span>{/if}
              {#if primary === u}<span class="ml-auto text-[10px] text-primary-500 font-medium">main</span>{/if}
              {#if !m}
                <button onclick={() => removeCustomName(u)} class="{primary === u ? '' : 'ml-auto'} text-gray-300 hover:text-red-500 transition-colors" aria-label="Remove {u}">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              {/if}
            </label>
          {/each}
        </div>
      {/if}

      <button
        onclick={confirmMembers}
        disabled={selected.size === 0 || !primary || saving}
        class="w-full py-2.5 rounded-lg text-sm font-medium text-white bg-primary-500 hover:bg-primary-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >{saving ? 'Linking…' : `Confirm${selectedList.length > 1 ? ` (${selectedList.length} names)` : ''}`}</button>
      <button onclick={switchAccount} class="w-full mt-2 py-1.5 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
        Not me — sign out
      </button>
      {#if errorMessage}
        <p class="mt-3 text-xs text-red-500">{errorMessage}</p>
      {/if}

    {:else if stage === 'linked'}
      <div class="flex flex-col items-center gap-2 py-4">
        <svg class="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        <p class="text-sm text-gray-600 dark:text-gray-300">You're all set — redirecting…</p>
      </div>

    {:else if stage === 'error'}
      <p class="text-sm text-red-500 mb-3">{errorMessage || 'Something went wrong.'}</p>
      <button onclick={() => { stage = 'signed_out'; }} class="text-sm text-primary-500 hover:underline">Try again</button>
    {/if}
  </div>
</div>
