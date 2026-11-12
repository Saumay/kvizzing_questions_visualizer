<script lang="ts">
  import { getContext } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { getMemberColor, getMemberInitials } from '$lib/utils/memberColors';
  import { topicCls, topicLabel, topicHex } from '$lib/utils/topicColors';
  import { formatTime, formatDateTz } from '$lib/utils/time';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import QuestionCard from '$lib/components/QuestionCard.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import ActivityHeatmap from '$lib/components/ActivityHeatmap.svelte';

  let { data } = $props();
  const store = getContext<QuestionStore>('store');
  const usernameCtx = getContext<{ value: string } | undefined>('username');
  const tzCtx = getContext<{ value: string }>('timezone');

  const member = $derived(data.member);
  const isMe = $derived(usernameCtx?.value === member.username);

  let tab = $state<'asked' | 'solved' | 'liked' | 'sessions'>('asked');
  let selectedDate = $state<string | null>(null);
  let selectedTopic = $state<string | null>(null);
  let listEl: HTMLDivElement | undefined = $state();

  function primaryTopic(q: { question: { topics?: string[] } }): string {
    return q.question.topics?.[0] ?? 'general';
  }

  const askedQuestions = $derived(store.getQuestions({ asker: member.username }, 'newest'));
  const solvedQuestions = $derived(store.getQuestions({ solver: member.username }, 'newest'));

  // "Liked" is a public per-username table (question_likes), unlike "saved"
  // questions/sessions which the app treats as private to the logged-in
  // viewer - so this is safe to show on anyone's profile, fetched fresh per
  // member since it's not part of the preloaded bulk dataset.
  let likedQuestionIds = $state<Set<string>>(new Set());
  $effect(() => {
    const username = member.username;
    likedQuestionIds = new Set();
    (async () => {
      try {
        const { supabase } = await import('$lib/supabase');
        const { data: rows } = await supabase.from('question_likes').select('question_id').eq('username', username);
        if (rows) likedQuestionIds = new Set(rows.map(r => r.question_id));
      } catch {
        // Best-effort: the tab just shows empty if this fails.
      }
    })();
  });
  const allQuestions = $derived(store.getQuestions());
  const likedQuestions = $derived(allQuestions.filter(q => likedQuestionIds.has(q.id)));

  const hostedSessions = $derived(
    store.getSessions()
      .filter(s => s.quizmaster === member.username)
      .sort((a, b) => b.date.localeCompare(a.date))
  );

  function sessionTitle(s: (typeof hostedSessions)[number]): string {
    return s.quiz_type === 'connect' ? `${s.quizmaster}'s Connect Quiz` : (s.theme ?? s.summary ?? `${s.quizmaster}'s Quiz`);
  }

  const shown = $derived.by(() => {
    if (tab === 'liked') return likedQuestions;
    if (tab === 'sessions') return [];
    let list = tab === 'asked' ? askedQuestions : solvedQuestions;
    if (selectedDate) list = list.filter(q => q.date === selectedDate);
    if (selectedTopic) list = list.filter(q => primaryTopic(q) === selectedTopic);
    return list;
  });

  function jumpToDate(dateKey: string) {
    // Prefer whichever tab actually has questions on that day, so clicking a
    // heatmap cell never lands on an empty filtered list.
    const askedHasIt = askedQuestions.some(q => q.date === dateKey);
    const solvedHasIt = solvedQuestions.some(q => q.date === dateKey);
    if (tab === 'asked' && !askedHasIt && solvedHasIt) tab = 'solved';
    else if (tab === 'solved' && !solvedHasIt && askedHasIt) tab = 'asked';
    selectedDate = dateKey;
    listEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function jumpToTopic(topic: string) {
    // The breakdown above is asked-only, so that's the tab a topic click
    // should land on.
    tab = 'asked';
    selectedTopic = topic;
    listEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // Topic breakdown among this member's asked questions (primary topic only)
  const topicBreakdown = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const q of askedQuestions) {
      counts.set(primaryTopic(q), (counts.get(primaryTopic(q)) ?? 0) + 1);
    }
    const total = askedQuestions.length || 1;
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([topic, count]) => ({ topic, count, pct: Math.round((count / total) * 100) }));
  });

  const bg = $derived(getMemberColor(member.username, member.color));

  // Combined asked + solved activity, one entry per occurrence so days with
  // more questions count for more in the heatmap.
  const activityDates = $derived([...askedQuestions.map(q => q.date), ...solvedQuestions.map(q => q.date)]);
</script>

<svelte:head>
  <title>{member.display_name} · KVizzing</title>
</svelte:head>

<div class="max-w-4xl mx-auto px-4 sm:px-6 py-6 space-y-5">
  <!-- Header -->
  <div class="bg-ui-card border border-stone-200/80 dark:border-zinc-600/80 rounded-2xl shadow-sm p-5 sm:p-6">
    <div class="flex items-center gap-4">
      <div
        class="w-16 h-16 rounded-full flex items-center justify-center font-bold text-white text-xl flex-shrink-0"
        style="background-color: {bg};"
      >
        {getMemberInitials(member.display_name)}
      </div>
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <h1 class="font-bold text-gray-900 dark:text-white text-xl truncate">{member.display_name}</h1>
          {#if isMe}
            <span class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300">You</span>
          {/if}
        </div>
        <p class="text-xs text-gray-400 mt-0.5">KVizzing member</p>
      </div>
    </div>

    <!-- Stat chips -->
    <div class="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-5">
      <div class="bg-gray-50 dark:bg-gray-800/60 rounded-xl px-3 py-2.5 text-center">
        <p class="text-lg font-bold text-gray-900 dark:text-white">{member.questions_asked}</p>
        <p class="text-[10px] text-gray-400 mt-0.5">Asked</p>
      </div>
      <div class="bg-gray-50 dark:bg-gray-800/60 rounded-xl px-3 py-2.5 text-center">
        <p class="text-lg font-bold text-gray-900 dark:text-white">{member.questions_solved}</p>
        <p class="text-[10px] text-gray-400 mt-0.5">Solved</p>
      </div>
      <div class="bg-gray-50 dark:bg-gray-800/60 rounded-xl px-3 py-2.5 text-center">
        <p class="text-lg font-bold text-gray-900 dark:text-white">{member.total_attempts}</p>
        <p class="text-[10px] text-gray-400 mt-0.5">Attempts</p>
      </div>
      <div class="bg-gray-50 dark:bg-gray-800/60 rounded-xl px-3 py-2.5 text-center">
        <p class="text-lg font-bold text-gray-900 dark:text-white">{member.sessions_hosted}</p>
        <p class="text-[10px] text-gray-400 mt-0.5">Sessions hosted</p>
      </div>
      <div class="bg-gray-50 dark:bg-gray-800/60 rounded-xl px-3 py-2.5 text-center col-span-2 sm:col-span-1">
        <p class="text-lg font-bold text-gray-900 dark:text-white">{formatTime(member.avg_solve_time_seconds)}</p>
        <p class="text-[10px] text-gray-400 mt-0.5">Avg solve time</p>
      </div>
    </div>
  </div>

  <!-- Activity heatmap -->
  {#if activityDates.length > 0}
    <div class="bg-ui-card border border-stone-200/80 dark:border-zinc-600/80 rounded-2xl shadow-sm p-5">
      <h2 class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3">Activity (questions asked + solved, past year)</h2>
      <ActivityHeatmap dates={activityDates} onDayClick={jumpToDate} />
    </div>
  {/if}

  <!-- Topic breakdown -->
  {#if topicBreakdown.length > 0}
    <div class="bg-ui-card border border-stone-200/80 dark:border-zinc-600/80 rounded-2xl shadow-sm p-5">
      <h2 class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3">Favourite topics (by questions asked)</h2>
      <div class="space-y-2">
        {#each topicBreakdown as row}
          <button
            type="button"
            onclick={() => jumpToTopic(row.topic)}
            class="flex items-center gap-3 w-full text-left rounded-lg -mx-1 px-1 py-0.5 hover:bg-gray-50 dark:hover:bg-gray-800/60 transition-colors"
          >
            <span class="text-xs font-medium w-28 truncate {topicCls(row.topic)} rounded-md px-2 py-0.5 text-center">{topicLabel(row.topic)}</span>
            <div class="flex-1 h-2 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
              <div class="h-full rounded-full" style="width: {row.pct}%; background-color: {topicHex(row.topic)};"></div>
            </div>
            <span class="text-xs text-gray-400 w-10 text-right flex-shrink-0">{row.count}</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Asked / Solved tabs -->
  <div bind:this={listEl}>
    <div class="flex items-center gap-1 mb-3 flex-wrap">
      <button
        onclick={() => tab = 'asked'}
        class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {tab === 'asked'
          ? 'bg-primary-50 text-primary-600 dark:bg-primary-500/20 dark:text-primary-400'
          : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'}"
      >Asked ({askedQuestions.length})</button>
      <button
        onclick={() => tab = 'solved'}
        class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {tab === 'solved'
          ? 'bg-primary-50 text-primary-600 dark:bg-primary-500/20 dark:text-primary-400'
          : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'}"
      >Solved ({solvedQuestions.length})</button>
      <button
        onclick={() => tab = 'liked'}
        class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {tab === 'liked'
          ? 'bg-primary-50 text-primary-600 dark:bg-primary-500/20 dark:text-primary-400'
          : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'}"
      >Liked ({likedQuestions.length})</button>
      <button
        onclick={() => tab = 'sessions'}
        class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {tab === 'sessions'
          ? 'bg-primary-50 text-primary-600 dark:bg-primary-500/20 dark:text-primary-400'
          : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'}"
      >Sessions ({hostedSessions.length})</button>
      {#if (tab === 'asked' || tab === 'solved') && selectedDate}
        <span class="text-xs text-gray-400 dark:text-gray-500 ml-1 flex items-center gap-1">
          Date: {selectedDate}
          <button onclick={() => selectedDate = null} class="text-primary-600 dark:text-primary-400 hover:underline font-medium" aria-label="Clear date filter">&times;</button>
        </span>
      {/if}
      {#if (tab === 'asked' || tab === 'solved') && selectedTopic}
        <span class="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1">
          Topic: {topicLabel(selectedTopic)}
          <button onclick={() => selectedTopic = null} class="text-primary-600 dark:text-primary-400 hover:underline font-medium" aria-label="Clear topic filter">&times;</button>
        </span>
      {/if}
      {#if (tab === 'asked' || tab === 'solved') && (selectedDate || selectedTopic)}
        <button
          onclick={() => { selectedDate = null; selectedTopic = null; }}
          class="text-xs text-primary-600 dark:text-primary-400 hover:underline font-medium"
        >Clear all</button>
      {/if}
    </div>

    {#if tab === 'sessions'}
      {#if hostedSessions.length === 0}
        <EmptyState message="No sessions hosted yet" />
      {:else}
        <div class="space-y-2">
          {#each hostedSessions as session (session.id)}
            <a
              href="/session/{session.id}"
              class="flex items-center gap-3 bg-ui-card border border-stone-200/80 dark:border-zinc-600/80 rounded-xl px-4 py-3 shadow-sm hover:border-primary-300 hover:shadow-md transition-all"
            >
              <span class="text-xs text-gray-400 w-24 flex-shrink-0">{formatDateTz(session.date, tzCtx?.value ?? 'Europe/London')}</span>
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-900 dark:text-white truncate">{sessionTitle(session)}</p>
                <p class="text-xs text-gray-400">{session.question_count} questions{session.is_live ? ' · ⭐ Live quiz' : ''}</p>
              </div>
            </a>
          {/each}
        </div>
      {/if}
    {:else if shown.length === 0}
      <EmptyState message={selectedDate || selectedTopic ? 'No questions match these filters' : 'No questions here yet'} />
    {:else}
      <div class="space-y-3">
        {#each shown as question (question.id)}
          <QuestionCard {question} />
        {/each}
      </div>
    {/if}
  </div>
</div>
