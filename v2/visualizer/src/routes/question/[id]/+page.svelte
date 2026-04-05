<script lang="ts">
  import { getContext } from 'svelte';
  import { goto } from '$app/navigation';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { formatDateTz, formatDateTimeTz, formatTime } from '$lib/utils/time';
  import { topicCls, topicClsSecondary, topicLabel } from '$lib/utils/topicColors';
  import { filterHints } from '$lib/utils/hints';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import AnswerSubmission from '$lib/components/AnswerSubmission.svelte';
  import DiscussionThread from '$lib/components/DiscussionThread.svelte';
  import MediaGallery from '$lib/components/MediaGallery.svelte';
  import { displayText } from '$lib/utils/text';
  import { supabase } from '$lib/supabase';

  let { data } = $props();
  const store = getContext<QuestionStore>('store');
  const tzCtx = getContext<{ value: string }>('timezone');
  const usernameCtx = getContext<{ value: string } | undefined>('username');
  const likedIds = getContext<{ value: Set<string> } | undefined>('likedIds');
  const likeCounts = getContext<{ value: Map<string, number> } | undefined>('likeCounts');
  const savedIds = getContext<{ value: Set<string> } | undefined>('savedIds');
  const flaggedIds = getContext<{ value: Set<string> } | undefined>('flaggedIds');

  const question = $derived(data.question);
  const q = $derived(question.question);
  const a = $derived(question.answer);
  const stats = $derived(question.stats);
  const adj = $derived(store.getAdjacentQuestions(question.id));

  let discussionVisible = $state(false);
  let revealed = $state(false);

  // Like / Save / Flag state
  let liked = $state(false);
  let likeCount = $state(0);
  let saved = $state(false);
  $effect(() => { liked = likedIds?.value?.has(question.id) ?? false; });
  $effect(() => { likeCount = likeCounts?.value?.get(question.id) ?? 0; });
  $effect(() => { saved = savedIds?.value?.has(question.id) ?? false; });

  async function toggleLike() {
    const user = usernameCtx?.value || '';
    if (!user) return;
    if (liked) {
      liked = false;
      likeCount = Math.max(0, likeCount - 1);
      if (likedIds) { const next = new Set(likedIds.value); next.delete(question.id); likedIds.value = next; }
      if (likeCounts) { const next = new Map(likeCounts.value); next.set(question.id, Math.max(0, (next.get(question.id) ?? 1) - 1)); likeCounts.value = next; }
      await supabase.from('question_likes').delete().eq('question_id', question.id).eq('username', user);
    } else {
      liked = true;
      likeCount = likeCount + 1;
      if (likedIds) likedIds.value = new Set([...likedIds.value, question.id]);
      if (likeCounts) { const next = new Map(likeCounts.value); next.set(question.id, (next.get(question.id) ?? 0) + 1); likeCounts.value = next; }
      await supabase.from('question_likes').upsert({ question_id: question.id, username: user }, { onConflict: 'question_id,username' });
    }
  }

  async function toggleSave() {
    const user = usernameCtx?.value || '';
    if (!user || !savedIds) return;
    if (saved) {
      saved = false;
      const next = new Set(savedIds.value); next.delete(question.id); savedIds.value = next;
      await supabase.from('question_saves').delete().eq('question_id', question.id).eq('username', user);
    } else {
      saved = true;
      savedIds.value = new Set([...savedIds.value, question.id]);
      await supabase.from('question_saves').upsert({ question_id: question.id, username: user }, { onConflict: 'question_id,username' });
    }
  }

  let flagged = $state(false);
  let showFlagModal = $state(false);
  let flagReason = $state('');
  $effect(() => { flagged = flaggedIds?.value?.has(question.id) ?? false; });

  function toggleFlag() {
    if (flagged) { unflag(); return; }
    showFlagModal = true;
    flagReason = '';
  }

  async function submitFlag(reason: string) {
    const user = usernameCtx?.value || '';
    if (!user) { showFlagModal = false; return; }
    showFlagModal = false;
    flagged = true;
    if (flaggedIds) flaggedIds.value = new Set([...flaggedIds.value, question.id]);
    await supabase.from('question_flags').upsert(
      { question_id: question.id, reporter: user, reason },
      { onConflict: 'question_id,reporter' }
    );
  }

  async function unflag() {
    const user = usernameCtx?.value || '';
    if (!user) return;
    flagged = false;
    if (flaggedIds) {
      const next = new Set(flaggedIds.value); next.delete(question.id); flaggedIds.value = next;
    }
    await supabase.from('question_flags').delete().eq('question_id', question.id).eq('reporter', user);
  }

  const questionMedia = $derived((q.media ?? []).filter((m: { url: string | null }) => m.url));
  const answerMedia = $derived(
    (question.discussion ?? [])
      .filter((d: { role: string; media?: { url: string | null }[] | null }) =>
        d.role === 'answer_reveal' && d.media?.some(m => m.url))
      .flatMap((d: { media?: { url: string | null }[] | null }) => d.media ?? [])
      .filter((m: { url: string | null }) => m.url)
  );

  function onAnswerReveal() {
    revealed = true;
  }
  function onAnswerHide() {
    revealed = false;
  }
</script>

<svelte:head>
  <title>{q.asker}'s question — KVizzing</title>
</svelte:head>

<div class="space-y-5">
  <!-- Back nav -->
  <div class="flex items-center gap-3">
    <a href="/" class="inline-flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
      </svg>
      Feed
    </a>
    {#if question.session}
      <span class="text-gray-300 dark:text-gray-600">/</span>
      <a href="/session/{question.session.id}" class="text-sm text-primary-500 dark:text-primary-400 hover:text-primary-600 dark:hover:text-primary-300 transition-colors">
        {question.session.quiz_type === 'connect' ? `${question.session.quizmaster}'s Connect Quiz` : (question.session.theme ?? 'Session')} #{question.session.question_number}
      </a>
    {/if}
    <button
      onclick={() => { const q = store.random(); if (q) goto(`/question/${q.id}`); }}
      class="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-primary-500 dark:bg-primary-600 text-white hover:bg-primary-600 dark:hover:bg-primary-700 rounded-lg transition-colors cursor-pointer flex-shrink-0"
    >
      <svg class="w-4 h-4 flex-shrink-0 animate-spin" style="animation-duration:1s" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
      <span class="hidden sm:inline">Random question</span>
      <span class="sm:hidden">Random</span>
    </button>
  </div>

  <!-- Context bar -->
  <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 sm:gap-3">
    <div class="flex items-center gap-2 min-w-0">
      <MemberAvatar username={q.asker} size="sm" />
      <div class="min-w-0">
        <p class="text-sm font-semibold text-gray-800 dark:text-gray-200">{q.asker}</p>
        <p class="text-xs text-gray-400 dark:text-gray-500">{question.question.timestamp ? formatDateTimeTz(question.question.timestamp, tzCtx?.value ?? 'Europe/London') : formatDateTz(question.date, tzCtx?.value ?? 'Europe/London')}</p>
      </div>
    </div>

    <div class="flex items-center gap-2 flex-wrap min-w-0 sm:justify-end sm:flex-shrink-0">
      {#if question.session}
        <a
          href="/session/{question.session.id}"
          class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 hover:bg-primary-200 dark:hover:bg-primary-900/60 transition-colors"
        >
          #{question.session.question_number} {question.session.quiz_type === 'connect' ? `${question.session.quizmaster}'s Connect Quiz` : (question.session.theme ?? 'Session')}
        </a>
      {/if}
      {#each (q.topics ?? []) as topic, i}
        <a href="/?topic={topic}" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium transition-colors {i === 0 ? topicCls(topic) : topicClsSecondary(topic)}">
          {topicLabel(topic)}
        </a>
      {/each}
    </div>
  </div>

  <!-- Question card -->
  <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-6 space-y-3">
    <p class="text-gray-900 dark:text-gray-100 text-base leading-relaxed font-medium">{displayText(q.text, questionMedia.length > 0)}</p>
    {#if questionMedia.length > 0}
      <MediaGallery attachments={questionMedia} />
    {:else if q.has_media}
      <p class="text-sm text-purple-500 dark:text-purple-400 flex items-center gap-1.5">
        <span>📎</span> Media not yet hosted
      </p>
    {/if}
    {#if revealed && q.tags && q.tags.length > 0}
      <div class="flex gap-2 flex-wrap">
        {#each q.tags as tag}
          <a href="/?tag={encodeURIComponent(tag)}" class="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">{tag}</a>
        {/each}
      </div>
    {/if}

    <!-- Like / Save / Flag actions -->
    <div class="flex items-center justify-between pt-3 border-t border-gray-100 dark:border-gray-700">
      <button
        onclick={toggleLike}
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {liked ? 'text-red-500 dark:text-red-400' : 'text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400'}"
      >
        <svg class="w-4 h-4" fill={liked ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
        </svg>
        {liked ? 'Liked' : 'Like'}{#if likeCount > 0}<span class="text-xs opacity-70">({likeCount})</span>{/if}
      </button>
      <div class="flex items-center gap-1">
        <button
          onclick={toggleSave}
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {saved ? 'text-primary-500 dark:text-primary-400' : 'text-gray-400 dark:text-gray-500 hover:text-primary-500 dark:hover:text-primary-400'}"
        >
          <svg class="w-4 h-4" fill={saved ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
          </svg>
          {saved ? 'Saved' : 'Save'}
        </button>
        <button
          onclick={toggleFlag}
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {flagged ? 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20' : 'text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400'}"
        >
          <svg class="w-4 h-4" fill={flagged ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 21v-4m0 0V5a2 2 0 012-2h6.5l1 1H21l-3 6 3 6h-8.5l-1-1H5a2 2 0 00-2 2z" />
          </svg>
          {flagged ? 'Flagged' : 'Flag'}
        </button>
      </div>
    </div>
  </div>

  <!-- Answer submission -->
  {#if a?.text}
    <AnswerSubmission
      correctAnswer={a.text}
      solver={a.solver ?? null}
      parts={a.parts && a.parts.length > 1 ? a.parts : null}
      hints={filterHints(question.discussion?.filter((d: {role: string}) => d.role === 'hint').map((d: {text: string}) => d.text) ?? [])}
      maxAttempts={3}
      onReveal={onAnswerReveal}
      onHide={onAnswerHide}
    />
  {/if}


  <!-- Answer reveal media -->
  {#if revealed && answerMedia.length > 0}
    <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-4">
      <p class="text-xs font-medium text-green-600 dark:text-green-400 uppercase tracking-wide mb-3">Answer reveal</p>
      <MediaGallery attachments={answerMedia} />
    </div>
  {/if}

  <!-- First solved by -->
  {#if revealed && a?.solver}
    <div class="flex items-center gap-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-xl px-4 py-3">
      <svg class="w-4 h-4 text-green-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <div class="flex items-center gap-2">
        <MemberAvatar username={a.solver} size="xs" />
        <span class="text-sm text-green-800 dark:text-green-200">
          First solved by <a href="/?solver={encodeURIComponent(a.solver)}" class="font-semibold hover:underline">{a.solver}</a>
        </span>
      </div>
      {#if a.confirmation_text}
        <span class="text-xs text-green-600 dark:text-green-400 ml-auto italic">"{a.confirmation_text}"</span>
      {/if}
    </div>
  {/if}

  <!-- Discussion Metrics -->
  {#if stats || question.discussion?.length > 0}
    <div class="space-y-3">
      <h2 class="text-sm font-semibold text-gray-700 dark:text-gray-300">Discussion Metrics</h2>

      {#if stats}
        {@const disc: any[] = question.discussion ?? []}
        {@const wrongAttempts: any[] = disc.filter((d: any) => d.role === 'attempt' && d.is_correct === false)}
        {@const hintEntries: any[] = disc.filter((d: any) => d.role === 'hint')}
        {@const participants = [...new Set(disc.filter((d: any) => d.role === 'attempt').map((d: any) => d.username))] as string[]}
        {@const wrongTooltip = wrongAttempts.length > 0 ? wrongAttempts.map((d: any) => `${d.username}: "${d.text?.slice(0, 50)}"`).join('\n') : ''}
        {@const hintTooltip = hintEntries.length > 0 ? hintEntries.map((d: any) => `"${d.text?.slice(0, 60)}"`).join('\n') : ''}
        {@const participantTooltip = participants.length > 0 ? participants.join(', ') : ''}
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {#if stats.time_to_answer_seconds}
            <div class="group/tip relative bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-center shadow-sm cursor-default">
              <p class="text-lg font-bold text-gray-900 dark:text-gray-100">{formatTime(stats.time_to_answer_seconds)}</p>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Solve time</p>
              <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg opacity-0 group-hover/tip:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-20">
                Time from question to first correct answer
              </div>
            </div>
          {/if}
          <div class="group/tip relative bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-center shadow-sm cursor-default">
            <p class="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.wrong_attempts}</p>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Wrong attempts</p>
            {#if wrongAttempts.length > 0}
              <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg opacity-0 group-hover/tip:opacity-100 transition-opacity pointer-events-auto z-20 min-w-[180px] max-w-[280px] text-left max-h-[200px] overflow-y-auto scrollbar-hide">
                {#each wrongAttempts as wa}
                  <p class="truncate py-0.5"><span class="font-medium">{wa.username}:</span> {wa.text?.slice(0, 50)}</p>
                {/each}
              </div>
            {/if}
          </div>
          {#if stats.hints_given > 0}
            <div class="group/tip relative bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-center shadow-sm cursor-default">
              <p class="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.hints_given}</p>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Hints given</p>
              <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg opacity-0 group-hover/tip:opacity-100 transition-opacity pointer-events-none z-20 min-w-[160px] max-w-[260px] text-left">
                {#each hintEntries.slice(0, 4) as h}
                  <p class="truncate">{h.text?.slice(0, 50)}</p>
                {/each}
                {#if hintEntries.length > 4}
                  <p class="text-gray-400 mt-0.5">+{hintEntries.length - 4} more</p>
                {/if}
              </div>
            </div>
          {/if}
          {#if stats.unique_participants > 0}
            <div class="group/tip relative bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-center shadow-sm cursor-default">
              <p class="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.unique_participants}</p>
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Participants</p>
              <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg opacity-0 group-hover/tip:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-20">
                {participantTooltip}
              </div>
            </div>
          {/if}
        </div>
      {/if}

  <!-- Discussion thread -->
  {#if question.discussion?.length > 0}
    <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
      <button
        class="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        onclick={() => discussionVisible = !discussionVisible}
      >
        <div class="flex items-center gap-2">
          <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <span class="text-sm font-semibold text-gray-700 dark:text-gray-300">Complete Discussion</span>
          <span class="text-xs text-gray-500 dark:text-gray-300 bg-gray-100 dark:bg-gray-600 px-2 py-0.5 rounded-full">{question.discussion.length}</span>
        </div>
        <svg class="w-4 h-4 text-gray-400 transition-transform {discussionVisible ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {#if discussionVisible}
        <div class="px-5 pb-5 border-t border-gray-100 dark:border-gray-700">
          <div class="pt-4">
            <DiscussionThread entries={question.discussion} />
          </div>
        </div>
      {/if}
    </div>
  {/if}

    </div>
  {/if}

  <!-- Prev / Next navigation -->
  <div class="flex justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
    {#if adj.next}
      <a href="/question/{adj.next.id}" class="flex items-center gap-2 text-sm text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group max-w-[45%] min-w-0">
        <svg class="w-4 h-4 flex-shrink-0 group-hover:-translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        <div class="min-w-0">
          <p class="text-xs text-gray-400 dark:text-gray-500">Previous</p>
          <p class="text-xs font-medium text-gray-700 dark:text-gray-300 group-hover:text-primary-600 dark:group-hover:text-primary-400 line-clamp-2">{adj.next.question.text.slice(0, 60)}…</p>
        </div>
      </a>
    {:else}
      <div></div>
    {/if}

    {#if adj.prev}
      <a href="/question/{adj.prev.id}" class="flex items-center gap-2 text-sm text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group text-right max-w-[45%] min-w-0">
        <div class="min-w-0">
          <p class="text-xs text-gray-400 dark:text-gray-500">Next</p>
          <p class="text-xs font-medium text-gray-700 dark:text-gray-300 group-hover:text-primary-600 dark:group-hover:text-primary-400 line-clamp-2">{adj.prev.question.text.slice(0, 60)}…</p>
        </div>
        <svg class="w-4 h-4 flex-shrink-0 group-hover:translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </a>
    {:else}
      <div></div>
    {/if}
  </div>
</div>

<!-- Flag modal -->
{#if showFlagModal}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onclick={() => showFlagModal = false}>
    <div class="bg-ui-card rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4 space-y-4" onclick={(e) => e.stopPropagation()}>
      <h3 class="text-lg font-bold text-gray-900 dark:text-gray-100">Flag this question</h3>
      <p class="text-sm text-gray-500 dark:text-gray-400">Why should this question be flagged?</p>
      <textarea
        bind:value={flagReason}
        placeholder="Reason (optional)"
        class="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 resize-none"
        rows="3"
      ></textarea>
      <div class="flex justify-end gap-2">
        <button onclick={() => showFlagModal = false} class="px-4 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors">Cancel</button>
        <button onclick={() => submitFlag(flagReason)} class="px-4 py-2 text-sm font-medium bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors">Flag</button>
      </div>
    </div>
  </div>
{/if}
