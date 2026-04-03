<script lang="ts">
  import { onMount } from 'svelte';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import { page } from '$app/stores';
  import { supabase } from '$lib/supabase';

  let { data } = $props();

  type Candidate = { timestamp: string; username: string; text: string; reason_flagged: string };
  type Thread = { id: string; date: string; candidates: Candidate[]; context: string[] };
  type Status = 'valid' | 'not_valid' | 'maybe';
  type Vote = { thread_id: string; reviewer: string; status: Status; reason: string; comment: string };

  const threads: Thread[] = data.threads;

  // ── Reviewer identity ──────────────────────────────────────────────────────
  let reviewer = $state('');
  let showNamePrompt = $state(false);

  onMount(() => {
    const saved = localStorage.getItem('kvizzing-reviewer-name') || '';
    if (saved) { reviewer = saved; loadVotes(); }
    else showNamePrompt = true;
  });

  function setName() {
    const name = reviewer.trim();
    if (!name) return;
    reviewer = name;
    localStorage.setItem('kvizzing-reviewer-name', name);
    showNamePrompt = false;
    loadVotes();
  }

  // ── Votes from Supabase ────────────────────────────────────────────────────
  // allVotes: every vote from every reviewer
  let allVotes = $state<Vote[]>([]);
  let loading = $state(true);

  async function loadVotes() {
    loading = true;
    const { data: rows, error } = await supabase.from('votes').select('*');
    if (!error && rows) allVotes = rows;
    loading = false;
  }

  // My votes (derived from allVotes)
  const myVotes = $derived(
    new Map(allVotes.filter(v => v.reviewer === reviewer).map(v => [v.thread_id, v]))
  );

  // Vote tallies per thread
  function voteTally(threadId: string) {
    const tv = allVotes.filter(v => v.thread_id === threadId);
    return {
      valid: tv.filter(v => v.status === 'valid').length,
      maybe: tv.filter(v => v.status === 'maybe').length,
      not_valid: tv.filter(v => v.status === 'not_valid').length,
      total: tv.length,
      votes: tv,
    };
  }

  // ── Voting ─────────────────────────────────────────────────────────────────
  let reasonOpenFor = $state<{ id: string; status: Status } | null>(null);
  let customReasonText = $state('');

  function startVote(id: string, status: Status) {
    const existing = myVotes.get(id);
    if (existing?.status === status) {
      // Toggle off — delete vote
      deleteVote(id);
      reasonOpenFor = null;
      return;
    }
    reasonOpenFor = { id, status };
    customReasonText = '';
  }

  async function confirmVote(reason: string) {
    if (!reasonOpenFor || !reviewer) return;
    const { id, status } = reasonOpenFor;

    const vote = { thread_id: id, reviewer, status, reason, comment: '' };

    // Optimistic update
    const idx = allVotes.findIndex(v => v.thread_id === id && v.reviewer === reviewer);
    if (idx >= 0) allVotes[idx] = { ...allVotes[idx], ...vote };
    else allVotes = [...allVotes, vote as Vote];

    reasonOpenFor = null;
    customReasonText = '';

    // Upsert to Supabase
    await supabase.from('votes').upsert(vote, { onConflict: 'thread_id,reviewer' });
  }

  async function deleteVote(threadId: string) {
    allVotes = allVotes.filter(v => !(v.thread_id === threadId && v.reviewer === reviewer));
    await supabase.from('votes').delete().eq('thread_id', threadId).eq('reviewer', reviewer);
  }

  function submitCustomReason() {
    if (customReasonText.trim()) confirmVote(customReasonText.trim());
  }

  const reasonPresets: Record<Status, string[]> = {
    valid: [
      'Genuine trivia question',
      'Bonus/follow-up question',
      'Quiz session question missed',
      'Unanswered but valid question',
    ],
    maybe: [
      'Needs more context',
      'Borderline — could be trivia',
      'Interesting discussion point',
      'Partially a question',
    ],
    not_valid: [
      'Guess/answer attempt',
      'Casual conversation',
      'Meta/admin discussion',
      'Rhetorical question',
    ],
  };

  // ── Filters ────────────────────────────────────────────────────────────────
  let filterStatus = $state<'all' | 'unreviewed' | 'valid' | 'maybe' | 'not_valid'>('all');
  const allDates = [...new Set(threads.map(t => t.date))].sort();
  const urlDate = $page.url.searchParams.get('date');
  let openDates = $state<Set<string>>(new Set(urlDate && allDates.includes(urlDate) ? [urlDate] : allDates.length > 0 ? [allDates[0]] : []));

  function filterThreads(threadList: Thread[]): Thread[] {
    return threadList.filter(t => {
      const mv = myVotes.get(t.id);
      if (filterStatus === 'unreviewed' && mv) return false;
      if (filterStatus === 'valid' && mv?.status !== 'valid') return false;
      if (filterStatus === 'maybe' && mv?.status !== 'maybe') return false;
      if (filterStatus === 'not_valid' && mv?.status !== 'not_valid') return false;
      return true;
    });
  }

  const filtered = $derived(filterThreads(threads));

  function toggleDate(d: string) {
    const next = new Set(openDates);
    if (next.has(d)) next.delete(d); else next.add(d);
    openDates = next;
  }

  function dateReviewStats(d: string) {
    const dateThreads = threads.filter(t => t.date === d);
    const total = dateThreads.length;
    const reviewed = dateThreads.filter(t => myVotes.has(t.id)).length;
    return { total, reviewed, done: reviewed === total };
  }

  // ── Stats ──────────────────────────────────────────────────────────────────
  const total = threads.length;
  const reviewed = $derived(myVotes.size);
  const valid = $derived([...myVotes.values()].filter(v => v.status === 'valid').length);
  const maybe = $derived([...myVotes.values()].filter(v => v.status === 'maybe').length);
  const notValid = $derived([...myVotes.values()].filter(v => v.status === 'not_valid').length);
  const pctValid = $derived(total > 0 ? valid / total * 100 : 0);
  const pctMaybe = $derived(total > 0 ? maybe / total * 100 : 0);
  const pctNot = $derived(total > 0 ? notValid / total * 100 : 0);
  const pctReviewed = $derived(total > 0 ? Math.round(reviewed / total * 100) : 0);

  // ── UI state ───────────────────────────────────────────────────────────────
  let expandedIds = $state<Set<string>>(new Set());
  function toggle(id: string) {
    const next = new Set(expandedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    expandedIds = next;
  }

  function exportValid() {
    const validThreads = threads
      .filter(t => myVotes.get(t.id)?.status === 'valid')
      .map(t => ({ id: t.id, date: t.date, candidates: t.candidates, reason: myVotes.get(t.id)?.reason }));
    const blob = new Blob([JSON.stringify(validThreads, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `missed-questions-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const reasonLabels: Record<string, string> = {
    question_mark: '?', question_prefix: 'Q:', media_short_text: 'Media', session_marker: 'Session',
  };
  const reasonColors: Record<string, string> = {
    question_mark: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    question_prefix: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
    media_short_text: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    session_marker: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  };
</script>

<!-- Name prompt overlay -->
{#if showNamePrompt}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
    <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-6 w-full max-w-sm space-y-4">
      <h2 class="text-lg font-bold text-gray-900 dark:text-gray-100">Welcome, reviewer!</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400">Enter your name to start reviewing. This is how your votes will be attributed.</p>
      <input
        type="text"
        placeholder="Your name"
        bind:value={reviewer}
        onkeydown={(e) => { if (e.key === 'Enter') setName(); }}
        class="w-full text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100"
        autofocus
      />
      <button
        onclick={setName}
        disabled={!reviewer.trim()}
        class="w-full px-4 py-2 text-sm font-medium rounded-lg transition-colors {reviewer.trim() ? 'bg-primary-500 text-white hover:bg-primary-600' : 'bg-gray-200 text-gray-400 cursor-not-allowed'}"
      >Start Reviewing</button>
    </div>
  </div>
{/if}

<div class="space-y-5">
  <!-- Hero tile -->
  <div class="bg-gradient-to-br from-primary-300 to-primary-900 rounded-2xl pt-3 sm:pt-6 px-6 pb-5 sm:pb-6 text-white shadow-lg relative">
    <div class="flex items-center justify-between mb-1">
      <h1 class="text-2xl font-bold">Review Candidate Questions</h1>
      {#if reviewer}
        <button
          onclick={() => showNamePrompt = true}
          class="text-xs text-primary-100 hover:text-white transition-colors flex items-center gap-1"
        >
          <MemberAvatar username={reviewer} size="xs" />
          {reviewer}
        </button>
      {/if}
    </div>
    <p class="text-primary-100 text-sm mb-4">Help us catch any trivia questions our pipeline might have missed.<br>Your reviews make the archive better for everyone. Thank you for contributing! ❤️</p>
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-baseline gap-2 text-sm">
        <span class="font-semibold">Reviewed {reviewed}/{total}</span>
        <span class="text-primary-200">{pctReviewed}% complete</span>
      </div>
    </div>
    <div class="mt-3 h-2 bg-white/20 rounded-full overflow-hidden">
      <div class="h-full flex">
        {#if pctValid > 0}<div class="bg-green-400 transition-all duration-300" style="width: {pctValid}%"></div>{/if}
        {#if pctMaybe > 0}<div class="bg-yellow-300 transition-all duration-300" style="width: {pctMaybe}%"></div>{/if}
        {#if pctNot > 0}<div class="bg-red-400 transition-all duration-300" style="width: {pctNot}%"></div>{/if}
      </div>
    </div>
  </div>

  {#if loading}
    <div class="text-center py-8">
      <p class="text-sm text-gray-400">Loading votes...</p>
    </div>
  {:else}

  <!-- Category filter pills -->
  <div class="space-y-2 sm:space-y-0 sm:flex sm:flex-wrap sm:gap-2">
    <div class="grid grid-cols-2 gap-2 sm:contents">
      <button onclick={() => filterStatus = 'all'} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterStatus === 'all' ? 'bg-primary-500 text-white shadow-sm' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}">
        All <span class="font-bold">{total}</span>
      </button>
      <button onclick={() => filterStatus = 'unreviewed'} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterStatus === 'unreviewed' ? 'bg-gray-500 text-white shadow-sm' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}">
        <span class="w-2 h-2 rounded-full bg-gray-400 {filterStatus === 'unreviewed' ? 'bg-white' : ''}"></span>
        Pending <span class="font-bold">{total - reviewed}</span>
      </button>
    </div>
    <div class="grid grid-cols-3 gap-2 sm:contents">
      <button onclick={() => filterStatus = 'valid'} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterStatus === 'valid' ? 'bg-green-500 text-white shadow-sm' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}">
        <span class="w-2 h-2 rounded-full bg-green-500 {filterStatus === 'valid' ? 'bg-white' : ''}"></span>
        Missed Q <span class="font-bold">{valid}</span>
      </button>
      <button onclick={() => filterStatus = 'maybe'} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterStatus === 'maybe' ? 'bg-yellow-500 text-white shadow-sm' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}">
        <span class="w-2 h-2 rounded-full bg-yellow-400 {filterStatus === 'maybe' ? 'bg-white' : ''}"></span>
        Maybe <span class="font-bold">{maybe}</span>
      </button>
      <button onclick={() => filterStatus = 'not_valid'} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterStatus === 'not_valid' ? 'bg-red-500 text-white shadow-sm' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'}">
        <span class="w-2 h-2 rounded-full bg-red-400 {filterStatus === 'not_valid' ? 'bg-white' : ''}"></span>
        Not a Q <span class="font-bold">{notValid}</span>
      </button>
    </div>
  </div>

  <!-- Date accordion sections -->
  <div class="space-y-3">
    {#each allDates as date}
      {@const stats = dateReviewStats(date)}
      {@const dateFiltered = filterThreads(threads.filter(t => t.date === date))}
      {#if dateFiltered.length > 0}
      <div class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <button
          onclick={() => toggleDate(date)}
          class="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
        >
          <div class="flex items-center gap-3">
            <svg class="w-4 h-4 text-gray-400 transition-transform {openDates.has(date) ? 'rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>
            <h2 class="text-sm font-semibold text-gray-900 dark:text-gray-100">{date}</h2>
            <span class="text-xs text-gray-400 dark:text-gray-500">{dateFiltered.length} thread{dateFiltered.length > 1 ? 's' : ''}</span>
          </div>
          <div class="flex items-center gap-2">
            <div class="w-16 h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
              <div class="h-full bg-green-400 rounded-full transition-all duration-300" style="width: {stats.total > 0 ? stats.reviewed / stats.total * 100 : 0}%"></div>
            </div>
            <span class="text-[10px] text-gray-400 dark:text-gray-500 w-8 text-right">{stats.reviewed}/{stats.total}</span>
            {#if stats.done}
              <svg class="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
              </svg>
            {/if}
          </div>
        </button>

        {#if openDates.has(date)}
        <div class="border-t border-gray-100 dark:border-gray-700 p-3 space-y-3">
    {#each dateFiltered as thread (thread.id)}
      {@const myVote = myVotes.get(thread.id)}
      {@const status = myVote?.status}
      {@const tally = voteTally(thread.id)}
      <div class="bg-ui-card rounded-xl border overflow-hidden transition-all {status === 'valid' ? 'border-green-300 dark:border-green-700 bg-green-50/30 dark:bg-green-900/10' : status === 'maybe' ? 'border-yellow-300 dark:border-yellow-700 bg-yellow-50/30 dark:bg-yellow-900/10' : status === 'not_valid' ? 'border-red-200 dark:border-red-800 opacity-50' : 'border-gray-200 dark:border-gray-700'}">
        <div class="p-4">
          {#each thread.candidates as cand, ci}
            <div class="flex items-start gap-3 {ci > 0 ? 'mt-3 pt-3 border-t border-gray-100 dark:border-gray-700' : ''}">
              <MemberAvatar username={cand.username} />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-sm font-medium text-gray-900 dark:text-gray-100">{cand.username}</span>
                  <span class="text-xs text-gray-400">{thread.date} {cand.timestamp.slice(11, 19)} UTC</span>
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-medium {reasonColors[cand.reason_flagged] ?? 'bg-gray-100 text-gray-600'}">
                    {reasonLabels[cand.reason_flagged] ?? cand.reason_flagged}
                  </span>
                </div>
                <p class="text-sm text-gray-800 dark:text-gray-200 mt-1 leading-relaxed">{cand.text}</p>
              </div>
            </div>
          {/each}

          <!-- Vote tally from all reviewers -->
          {#if tally.total > 0}
            <div class="mt-3 flex items-center gap-3 text-xs">
              {#if tally.valid > 0}
                <span class="text-green-600 dark:text-green-400 font-medium">{tally.valid} missed Q</span>
              {/if}
              {#if tally.maybe > 0}
                <span class="text-yellow-600 dark:text-yellow-400 font-medium">{tally.maybe} maybe</span>
              {/if}
              {#if tally.not_valid > 0}
                <span class="text-red-500 dark:text-red-400 font-medium">{tally.not_valid} not a Q</span>
              {/if}
              <span class="text-gray-400 dark:text-gray-500">({tally.total} vote{tally.total > 1 ? 's' : ''})</span>
            </div>
          {/if}

          <!-- Actions row -->
          <div class="mt-3 flex items-center justify-between">
            <button
              onclick={() => toggle(thread.id)}
              class="text-xs text-primary-500 dark:text-primary-400 hover:text-primary-600 flex items-center gap-1"
            >
              <svg class="w-3 h-3 transition-transform {expandedIds.has(thread.id) ? 'rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
              {expandedIds.has(thread.id) ? 'Hide' : 'Show'} context
            </button>
            <div class="flex items-center gap-1.5">
              <button
                onclick={() => startVote(thread.id, 'valid')}
                class="px-3 py-1 rounded-lg text-xs font-medium transition-all {status === 'valid' ? 'bg-green-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 hover:bg-green-100 hover:text-green-700 dark:hover:bg-green-900/30 dark:hover:text-green-400'}"
              >Missed Q</button>
              <button
                onclick={() => startVote(thread.id, 'maybe')}
                class="px-3 py-1 rounded-lg text-xs font-medium transition-all {status === 'maybe' ? 'bg-yellow-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 hover:bg-yellow-100 hover:text-yellow-700 dark:hover:bg-yellow-900/30 dark:hover:text-yellow-400'}"
              >Maybe</button>
              <button
                onclick={() => startVote(thread.id, 'not_valid')}
                class="px-3 py-1 rounded-lg text-xs font-medium transition-all {status === 'not_valid' ? 'bg-red-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 hover:bg-red-100 hover:text-red-700 dark:hover:bg-red-900/30 dark:hover:text-red-400'}"
              >Not a Q</button>
            </div>
          </div>

          <!-- Reason picker -->
          {#if reasonOpenFor?.id === thread.id}
            {@const presets = reasonPresets[reasonOpenFor.status]}
            {@const statusColors = { valid: 'border-green-300 bg-green-50/50 dark:border-green-700 dark:bg-green-900/10', maybe: 'border-yellow-300 bg-yellow-50/50 dark:border-yellow-700 dark:bg-yellow-900/10', not_valid: 'border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-900/10' }}
            {@const chipColors = { valid: 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-300 dark:hover:bg-green-900/50', maybe: 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300 dark:hover:bg-yellow-900/50', not_valid: 'bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-300 dark:hover:bg-red-900/50' }}
            <div class="mt-3 p-3 rounded-lg border {statusColors[reasonOpenFor.status]}">
              <p class="text-[10px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Select a reason</p>
              <div class="flex flex-wrap gap-1.5 mb-2">
                {#each presets as preset}
                  <button
                    onclick={() => confirmVote(preset)}
                    class="px-2.5 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer {chipColors[reasonOpenFor.status]}"
                  >{preset}</button>
                {/each}
              </div>
              <div class="flex gap-2">
                <input
                  type="text"
                  placeholder="Or type a custom reason..."
                  bind:value={customReasonText}
                  onkeydown={(e) => { if (e.key === 'Enter') submitCustomReason(); }}
                  class="flex-1 text-xs border border-gray-200 dark:border-gray-600 rounded-lg px-2.5 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
                />
                <button
                  onclick={submitCustomReason}
                  disabled={!customReasonText.trim()}
                  class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors {customReasonText.trim() ? 'bg-primary-500 text-white hover:bg-primary-600' : 'bg-gray-200 text-gray-400 dark:bg-gray-700 dark:text-gray-500'}"
                >Send</button>
              </div>
            </div>
          {/if}

          <!-- Show saved reason + other votes -->
          {#if myVote?.reason && reasonOpenFor?.id !== thread.id}
            <div class="mt-2 text-xs text-gray-500 dark:text-gray-400 italic">
              You: "{myVote.reason}"
            </div>
          {/if}
          {#if tally.votes.filter(v => v.reviewer !== reviewer && v.reason).length > 0 && expandedIds.has(thread.id)}
            <div class="mt-2 space-y-1">
              {#each tally.votes.filter(v => v.reviewer !== reviewer && v.reason) as v}
                <div class="text-xs text-gray-400 dark:text-gray-500">
                  <span class="font-medium text-gray-500 dark:text-gray-400">{v.reviewer}:</span>
                  <span class="{v.status === 'valid' ? 'text-green-600 dark:text-green-400' : v.status === 'maybe' ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-500 dark:text-red-400'}">{v.status.replace('_', ' ')}</span>
                  — <span class="italic">"{v.reason}"</span>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Context as chat bubbles -->
        {#if expandedIds.has(thread.id)}
          <div class="border-t border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 px-4 py-3 max-h-80 overflow-y-auto space-y-2">
            {#each thread.context as line}
              {@const isHighlighted = line.startsWith('>>>')}
              {@const clean = line.replace(/^>>>\s*/, '').replace(/^\s+/, '')}
              {@const tsMatch = clean.match(/^\[([^\]]+)\]\s*(.+?):\s*([\s\S]*)$/)}
              {#if tsMatch}
                {@const ts = tsMatch[1]}
                {@const user = tsMatch[2]}
                {@const text = tsMatch[3]}
                <div class="flex items-start gap-2 {isHighlighted ? 'bg-primary-50 dark:bg-primary-900/20 -mx-2 px-2 py-1.5 rounded-lg border-l-3 border-primary-400' : ''}">
                  <MemberAvatar username={user} size="xs" />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-1.5">
                      <span class="text-xs font-medium {isHighlighted ? 'text-primary-700 dark:text-primary-300' : 'text-gray-700 dark:text-gray-300'}">{user}</span>
                      <span class="text-[10px] text-gray-400 dark:text-gray-500">{ts.slice(11, 19)}</span>
                    </div>
                    <p class="text-xs {isHighlighted ? 'text-primary-800 dark:text-primary-200 font-medium' : 'text-gray-600 dark:text-gray-400'} leading-relaxed">{text}</p>
                  </div>
                </div>
              {:else}
                <p class="text-xs text-gray-400 whitespace-pre-wrap">{clean}</p>
              {/if}
            {/each}
          </div>
        {/if}
      </div>
    {/each}
        </div>
        {/if}
      </div>
      {/if}
    {/each}
  </div>

  {#if filtered.length === 0}
    <div class="text-center py-12">
      <p class="text-gray-400 dark:text-gray-500">{reviewed === total ? 'All done! Export missed questions above.' : 'No threads match this filter.'}</p>
    </div>
  {/if}

  {/if}
</div>
