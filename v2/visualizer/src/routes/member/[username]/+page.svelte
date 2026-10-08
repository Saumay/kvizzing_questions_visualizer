<script lang="ts">
  import { getContext } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { getMemberColor, getMemberInitials } from '$lib/utils/memberColors';
  import { topicCls, topicLabel, topicHex } from '$lib/utils/topicColors';
  import { formatTime } from '$lib/utils/time';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import QuestionCard from '$lib/components/QuestionCard.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';

  let { data } = $props();
  const store = getContext<QuestionStore>('store');
  const usernameCtx = getContext<{ value: string } | undefined>('username');

  const member = $derived(data.member);
  const isMe = $derived(usernameCtx?.value === member.username);

  let tab = $state<'asked' | 'solved'>('asked');

  const askedQuestions = $derived(store.getQuestions({ asker: member.username }, 'newest'));
  const solvedQuestions = $derived(store.getQuestions({ solver: member.username }, 'newest'));
  const shown = $derived(tab === 'asked' ? askedQuestions : solvedQuestions);

  // Topic breakdown among this member's asked questions (primary topic only)
  const topicBreakdown = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const q of askedQuestions) {
      const primary = q.question.topics?.[0] ?? 'general';
      counts.set(primary, (counts.get(primary) ?? 0) + 1);
    }
    const total = askedQuestions.length || 1;
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([topic, count]) => ({ topic, count, pct: Math.round((count / total) * 100) }));
  });

  const bg = $derived(getMemberColor(member.username, member.color));
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

  <!-- Topic breakdown -->
  {#if topicBreakdown.length > 0}
    <div class="bg-ui-card border border-stone-200/80 dark:border-zinc-600/80 rounded-2xl shadow-sm p-5">
      <h2 class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3">Favourite topics (by questions asked)</h2>
      <div class="space-y-2">
        {#each topicBreakdown as row}
          <div class="flex items-center gap-3">
            <span class="text-xs font-medium w-28 truncate {topicCls(row.topic)} rounded-md px-2 py-0.5 text-center">{topicLabel(row.topic)}</span>
            <div class="flex-1 h-2 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
              <div class="h-full rounded-full" style="width: {row.pct}%; background-color: {topicHex(row.topic)};"></div>
            </div>
            <span class="text-xs text-gray-400 w-10 text-right flex-shrink-0">{row.count}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Asked / Solved tabs -->
  <div>
    <div class="flex gap-1 mb-3">
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
    </div>

    {#if shown.length === 0}
      <EmptyState message="No questions here yet" />
    {:else}
      <div class="space-y-3">
        {#each shown as question (question.id)}
          <QuestionCard {question} />
        {/each}
      </div>
    {/if}
  </div>
</div>
