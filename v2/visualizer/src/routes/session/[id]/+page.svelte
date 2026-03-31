<script lang="ts">
  import { getContext } from 'svelte';
  import { goto } from '$app/navigation';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import type { Question } from '$lib/types';
  import { formatDateTz, formatTime } from '$lib/utils/time';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import { topicCls, topicLabel, TOPICS } from '$lib/utils/topicColors';
  import { isCorrect, isAlmost } from '$lib/utils/fuzzy';
  import { filterHints } from '$lib/utils/hints';
  import { SESSION_IMAGE_OPACITY } from '$lib/config/ui';
  import SearchInput from '$lib/components/SearchInput.svelte';
  import FiltersToggleButton from '$lib/components/FiltersToggleButton.svelte';
  import TagFilter from '$lib/components/TagFilter.svelte';
  import TopicFilter from '$lib/components/TopicFilter.svelte';
  import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import ConnectBadge from '$lib/components/ConnectBadge.svelte';
  import { tagFrequency } from '$lib/utils/tags';

  let { data } = $props();
  const store = getContext<QuestionStore>('store');
  const tzCtx = getContext<{ value: string }>('timezone');

  const session = $derived(data.session);
  const sessionQuestions = $derived(data.sessionQuestions);
  const adj = $derived(store.getAdjacentSessions(session.id));

  const isConnect = $derived(session.quiz_type === 'connect');

  let revealAll = $state(false);
  let revealedIds = $state(new Set<string>());
  let hiddenIds = $state(new Set<string>());
  let inputs = $state(new Map<string, string>());
  let results = $state(new Map<string, 'correct' | 'almost' | 'wrong'>());
  let hintsShown = $state(new Map<string, number>());

  // Search & filters
  let search = $state('');
  let filtersOpen = $state(false);
  let filterAsker = $state('');
  let filterSolver = $state('');
  let filterHasMedia = $state<boolean | undefined>(undefined);
  let filterTopics = $state(new Set<string>());
  let filterTags = $state(new Set<string>());
  let sortBy = $state<'newest' | 'oldest' | 'quickest'>('newest');

  const askers = $derived([...new Set(sessionQuestions.map((q: Question) => q.question.asker))].filter(Boolean).sort());
  const solvers = $derived([...new Set(sessionQuestions.map((q: Question) => q.answer?.solver).filter(Boolean))].sort());

  const { tagFreq, allTags } = $derived(tagFrequency(sessionQuestions));

  const activeFilterCount = $derived(
    [isConnect ? '' : filterAsker, filterSolver].filter(Boolean).length +
    (filterHasMedia !== undefined ? 1 : 0) +
    (sortBy !== 'newest' ? 1 : 0) +
    filterTags.size + filterTopics.size
  );

  const filteredQuestions = $derived.by(() => {
    const q = search.trim().toLowerCase();
    let results = sessionQuestions.filter((question: Question) => {
      if (q && !question.question.text.toLowerCase().includes(q)) return false;
      if (filterAsker && question.question.asker !== filterAsker) return false;
      if (filterSolver && question.answer?.solver !== filterSolver) return false;
      if (filterHasMedia !== undefined && !!(question.question.image_url || question.question.audio_url) !== filterHasMedia) return false;
      if (filterTopics.size > 0 && !question.question.topics?.some((t: string) => filterTopics.has(t))) return false;
      if (filterTags.size > 0 && ![...filterTags].every(t => question.question.tags?.includes(t))) return false;
      return true;
    });
    if (sortBy === 'oldest') results = [...results].reverse();
    else if (sortBy === 'quickest') results = [...results].sort((a, b) => (a.answer?.time_to_answer_seconds ?? Infinity) - (b.answer?.time_to_answer_seconds ?? Infinity));
    return results;
  });

  const hasFilters = $derived(!!(search || filterAsker || filterSolver || filterHasMedia !== undefined || filterTopics.size > 0 || filterTags.size > 0 || sortBy !== 'newest'));

  function clearFilters() {
    search = '';
    filterAsker = '';
    filterSolver = '';
    filterHasMedia = undefined;
    filterTopics = new Set();
    filterTags = new Set();
    sortBy = 'newest';
  }

  const selectCls = "flex-1 basis-[calc(50%-4px)] sm:flex-none sm:w-[129px] text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600";
  const filterSizeCls = "flex-1 basis-[calc(50%-4px)] sm:flex-none sm:w-[129px]";

  // Connect quiz state
  let connectGuess = $state('');
  let connectResult = $state<'correct' | 'almost' | 'wrong' | null>(null);
  let connectRevealed = $state(false);

  function submitConnectGuess() {
    const input = connectGuess.trim();
    if (!input || !session.theme) return;
    if (isCorrect(input, session.theme)) { connectResult = 'correct'; connectRevealed = true; }
    else if (isAlmost(input, session.theme)) connectResult = 'almost';
    else connectResult = 'wrong';
  }

  function toggleReveal(id: string) {
    const next = new Set(revealedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    revealedIds = next;
  }

  function hideQuestion(id: string) {
    if (revealAll) {
      hiddenIds = new Set(hiddenIds).add(id);
    } else {
      const next = new Set(revealedIds);
      next.delete(id);
      revealedIds = next;
    }
    const nextResults = new Map(results);
    nextResults.delete(id);
    results = nextResults;
    inputs = new Map(inputs).set(id, '');
  }

  function submitGuess(id: string, correctAnswer: string) {
    const input = (inputs.get(id) ?? '').trim();
    if (!input) return;
    let result: 'correct' | 'almost' | 'wrong';
    if (isCorrect(input, correctAnswer)) result = 'correct';
    else if (isAlmost(input, correctAnswer)) result = 'almost';
    else result = 'wrong';
    results = new Map(results).set(id, result);
    if (result === 'correct') {
      revealedIds = new Set(revealedIds).add(id);
    }
  }
</script>

<svelte:head>
  <title>{isConnect && !connectRevealed ? `${session.quizmaster}'s Connect Quiz` : (session.theme ?? `${session.quizmaster}'s Quiz`)} — KVizzing</title>
</svelte:head>

<div class="space-y-6">
  <!-- Back nav -->
  <a href="/sessions" class="inline-flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
    </svg>
    All quiz sessions
  </a>

  <!-- Session header -->
  <div class="relative overflow-hidden bg-gray-900 rounded-2xl p-6 text-white shadow-lg">
    <div
      class="absolute inset-0 bg-cover bg-center transition-opacity"
      style="background-image: url('{session.quiz_type === 'connect' ? '/images/connect-quiz-bg.png' : '/images/sessions/' + session.id + '.jpg'}'); opacity: {SESSION_IMAGE_OPACITY.header}"
    ></div>
    <div class="relative">
    <div>
      <div class="flex items-center gap-2 mb-1">
        {#if isConnect}
          <ConnectBadge variant="on-dark" label="Connect Quiz" />
        {/if}
      </div>
      <h1 class="text-xl font-bold mb-1">
        {#if isConnect && !connectRevealed}
          {session.quizmaster}'s Connect Quiz
        {:else}
          {session.theme ?? `${session.quizmaster}'s Quiz`}
        {/if}
      </h1>
      <p class="text-primary-100 text-sm">
        Hosted by {session.quizmaster} · {formatDateTz(sessionQuestions[0]?.question?.timestamp ?? session.date, tzCtx?.value ?? 'Europe/London')}
      </p>
    </div>

    <!-- Stats row -->
    <div class="flex flex-wrap gap-6 mt-4 pt-4 border-t border-primary-400">
      <div>
        <p class="text-primary-200 text-xs">Questions</p>
        <p class="text-xl font-bold">{session.question_count}</p>
      </div>
      {#if session.participant_count}
        <div>
          <p class="text-primary-200 text-xs">Participants</p>
          <p class="text-xl font-bold">{session.participant_count}</p>
        </div>
      {/if}
      {#if session.avg_time_to_answer_seconds}
        <div>
          <p class="text-primary-200 text-xs">Avg solve time</p>
          <p class="text-xl font-bold">{formatTime(session.avg_time_to_answer_seconds)}</p>
        </div>
      {/if}
      {#if session.avg_wrong_attempts}
        <div>
          <p class="text-primary-200 text-xs">Avg wrong guesses</p>
          <p class="text-xl font-bold">{session.avg_wrong_attempts.toFixed(1)}</p>
        </div>
      {/if}
    </div>
    </div>
  </div>

  <!-- Controls -->
  <div class="space-y-3">
    <!-- Search + filters toggle + reveal all -->
    <div class="flex gap-2">
      <SearchInput bind:value={search} placeholder="Search questions…" />
      <FiltersToggleButton bind:open={filtersOpen} count={activeFilterCount} />
      <button
        onclick={() => { revealAll = !revealAll; revealedIds = new Set(); hiddenIds = new Set(); }}
        class="flex-none px-4 py-2 text-sm font-medium rounded-xl border transition-colors {revealAll ? 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600' : 'bg-primary-500 text-white border-primary-500 hover:bg-primary-600 dark:bg-primary-600 dark:border-primary-600'}"
      >
        {revealAll ? 'Hide all' : 'Reveal all'}
      </button>
    </div>

    {#if filtersOpen}
    <div class="space-y-2">
      <!-- Row 1: main filters -->
      <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        {#if !isConnect}
          <select bind:value={filterAsker} class={selectCls}>
            <option value="">All askers</option>
            {#each askers as asker}
              <option value={asker}>{asker}</option>
            {/each}
          </select>
        {/if}
        <select bind:value={filterSolver} class={selectCls}>
          <option value="">All solvers</option>
          {#each solvers as solver}
            <option value={solver}>{solver}</option>
          {/each}
        </select>
        <select bind:value={sortBy} class={selectCls}>
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="quickest">Quickest solve</option>
        </select>
        <div class="col-span-2 sm:col-auto sm:flex-none inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
          {#each ([undefined, true, false] as const) as val, i}
            <button
              onclick={() => filterHasMedia = val}
              class="flex-1 sm:flex-none px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors
                {filterHasMedia === val ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}
                {i > 0 ? 'border-l border-gray-200 dark:border-gray-600' : ''}"
            >{val === undefined ? 'All' : val ? 'Media' : 'No Media'}</button>
          {/each}
        </div>
      </div>
      <!-- Row 2: tag + topic filters -->
      <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        <TagFilter bind:tags={filterTags} {allTags} {tagFreq} class={filterSizeCls} />
        <TopicFilter bind:topics={filterTopics} class={selectCls} />
      </div>
    </div>
    {/if}

    <ActiveFilterChips bind:tags={filterTags} bind:topics={filterTopics} hasFilters={hasFilters} onClear={clearFilters} />

    <p class="text-sm text-gray-500 dark:text-gray-400">
      {filteredQuestions.length}{filteredQuestions.length !== sessionQuestions.length ? ` of ${sessionQuestions.length}` : ''} question{filteredQuestions.length !== 1 ? 's' : ''}
      {#if hasFilters}<span class="text-primary-500 font-medium"> (filtered)</span>{/if}
    </p>
  </div>

  <!-- Question grid -->
  {#if sessionQuestions.length === 0}
    <EmptyState emoji="🤔" message="No questions found for this session" />
  {:else if filteredQuestions.length === 0}
    <EmptyState message="No questions match your filters" onClear={clearFilters} />
  {:else}
    <div class="grid gap-4">
      {#each filteredQuestions as question, i (question.id)}
        {@const isRevealed = (revealAll && !hiddenIds.has(question.id)) || revealedIds.has(question.id)}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div
          class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden hover:shadow-md hover:border-gray-300 dark:hover:border-gray-600 transition-all cursor-pointer"
          onclick={(e) => { if (!(e.target as HTMLElement).closest('a,button,input')) goto(`/question/${question.id}`); }}
        >
          <!-- Question number badge + link -->
          <div class="p-4">
            <div class="flex items-start gap-3">
              <!-- Number badge -->
              <div class="w-7 h-7 rounded-lg bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300 font-bold text-sm flex items-center justify-center flex-shrink-0 mt-0.5">
                {i + 1}
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between gap-2 mb-2">
                  <div class="flex items-center gap-2">
                    <MemberAvatar username={question.question.asker} size="xs" />
                    <span class="text-xs font-medium text-gray-700 dark:text-gray-300">{question.question.asker}</span>
                  </div>
                  {#if question.question.topics?.[0]}
                    <a href="/?topic={question.question.topics[0]}" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium {topicCls(question.question.topics[0])} hover:opacity-80 transition-opacity flex-shrink-0">
                      {topicLabel(question.question.topics[0])}
                    </a>
                  {/if}
                </div>
                <a href="/question/{question.id}" class="text-sm text-gray-800 dark:text-gray-200 hover:text-primary-600 transition-colors leading-relaxed line-clamp-4 block">
                  {question.question.text}
                </a>

                <!-- Stats + tags row -->
                <div class="flex items-center justify-between gap-3 mt-2">
                  <div class="flex items-center gap-4 text-xs text-gray-400 dark:text-gray-500 min-w-0">
                    {#if question.stats?.time_to_answer_seconds}
                      <span class="flex items-center gap-1 flex-shrink-0">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        {formatTime(question.stats.time_to_answer_seconds)}
                      </span>
                    {/if}
                    {#if question.stats?.wrong_attempts > 0}
                      <span class="flex items-center gap-1 flex-shrink-0">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                        {question.stats.wrong_attempts} wrong
                      </span>
                    {/if}
                    {#if question.discussion?.length > 0}
                      <span class="flex items-center gap-1 flex-shrink-0">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                        {question.discussion.length} messages
                      </span>
                    {/if}
                  </div>
                  {#if isRevealed && question.question.tags?.length > 0}
                    <div class="flex gap-1 flex-wrap justify-end">
                      {#each question.question.tags as tag}
                        <a href="/?tag={encodeURIComponent(tag)}" onclick={(e) => e.stopPropagation()} class="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 hover:text-gray-700 dark:hover:text-gray-200 transition-colors whitespace-nowrap">{tag}</a>
                      {/each}
                    </div>
                  {/if}
                </div>
              </div>
            </div>
          </div>

          <!-- Answer area -->
          <div class="border-t border-gray-100 dark:border-gray-700">
            {#if isRevealed}
              <div class="px-3 py-2.5 min-h-[48px] bg-green-50 dark:bg-green-900/30 flex flex-wrap items-center gap-x-3 gap-y-1">
                <span class="text-xs font-medium text-green-600 dark:text-green-400 uppercase tracking-wide flex-shrink-0">Answer</span>
                <span class="text-sm font-semibold text-green-800 dark:text-green-200 flex-1 min-w-0">{question.answer?.text ?? '—'}</span>
                <div class="flex items-center gap-2 flex-shrink-0 ml-auto">
                  {#if question.answer?.solver}
                    <div class="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
                      <MemberAvatar username={question.answer.solver} size="xs" />
                      <span class="hidden sm:inline">{question.answer.solver}</span>
                    </div>
                  {/if}
                  <button
                    onclick={() => hideQuestion(question.id)}
                    class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                  >Hide</button>
                </div>
              </div>
            {:else}
              {@const result = results.get(question.id)}
              {@const hints = filterHints(question.discussion?.filter((d: {role: string}) => d.role === 'hint').map((d: {text: string}) => d.text) ?? [])}
              {@const shown = hintsShown.get(question.id) ?? 0}
              {#if shown > 0}
                <div class="px-4 py-2 bg-amber-50 dark:bg-amber-900/30 border-b border-amber-100 dark:border-amber-800 space-y-1">
                  {#each hints.slice(0, shown) as hint}
                    <p class="text-xs text-amber-700 dark:text-amber-300 flex items-start gap-1.5">
                      <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                      </svg>
                      {hint}
                    </p>
                  {/each}
                </div>
              {/if}
              <div class="px-3 py-2.5 flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Your answer…"
                  value={inputs.get(question.id) ?? ''}
                  oninput={(e) => { inputs = new Map(inputs).set(question.id, (e.target as HTMLInputElement).value); }}
                  onkeydown={(e) => { if (e.key === 'Enter') submitGuess(question.id, question.answer?.text ?? ''); }}
                  class="flex-1 min-w-0 px-2.5 py-2 text-xs border rounded-lg focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 transition-all
                    {result === 'correct' ? 'border-green-300 bg-green-50 dark:bg-green-900/30' : result === 'almost' ? 'border-amber-300 bg-amber-50 dark:bg-amber-900/30' : result === 'wrong' ? 'border-red-300 bg-red-50' : 'border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400'}"
                  autocomplete="off" spellcheck="false"
                  title={result === 'almost' ? 'Close! Try again.' : result === 'wrong' ? 'Not quite. Try again or reveal.' : ''}
                />
                <button
                  onclick={() => submitGuess(question.id, question.answer?.text ?? '')}
                  class="px-3 py-2 text-xs font-medium bg-primary-500 text-white rounded-lg hover:bg-primary-600 dark:bg-primary-600 transition-colors flex-shrink-0"
                >Submit</button>
                <div class="flex items-center gap-2 flex-shrink-0">
                  <button
                    onclick={() => hintsShown = new Map(hintsShown).set(question.id, Math.min(shown + 1, hints.length))}
                    disabled={hints.length === 0 || shown >= hints.length}
                    title={hints.length === 0 ? 'No hints available' : shown >= hints.length ? 'No more hints' : `Hint ${shown + 1} of ${hints.length}`}
                    class="p-1.5 rounded-lg transition-colors {hints.length === 0 || shown >= hints.length ? 'text-gray-300 cursor-default' : 'text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-900/20'}"
                  >
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </button>
                  <button
                    onclick={() => toggleReveal(question.id)}
                    class="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 font-medium transition-colors"
                  >Reveal</button>
                </div>
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}

  <!-- Connect: guess the theme panel -->
  {#if isConnect}
    <div class="rounded-xl border-2 {connectRevealed ? 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20' : 'border-dashed border-primary-300 dark:border-primary-700 bg-primary-50/50 dark:bg-primary-900/10'} p-5">
      <div class="flex items-center gap-2 mb-3">
        <svg class="w-4 h-4 {connectRevealed ? 'text-green-500' : 'text-primary-500'}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
        </svg>
        <h3 class="text-sm font-semibold {connectRevealed ? 'text-green-700 dark:text-green-300' : 'text-primary-700 dark:text-primary-300'}">
          {connectRevealed ? 'Connect revealed!' : 'Guess the connect'}
        </h3>
      </div>

      {#if connectRevealed}
        <p class="text-lg font-bold text-green-800 dark:text-green-200">{session.theme}</p>
        {#if connectResult === 'correct'}
          <p class="text-xs text-green-600 dark:text-green-400 mt-1">You got it!</p>
        {/if}
      {:else}
        <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">What's the common theme connecting all these questions?</p>
        <div class="flex gap-2">
          <input
            type="text"
            bind:value={connectGuess}
            placeholder="Your guess…"
            onkeydown={(e) => { if (e.key === 'Enter') submitConnectGuess(); }}
            class="flex-1 min-w-0 px-3 py-2 text-sm border rounded-lg focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 transition-all
              {connectResult === 'almost' ? 'border-amber-300 bg-amber-50 dark:bg-amber-900/30 dark:border-amber-700' : connectResult === 'wrong' ? 'border-red-300 bg-red-50 dark:bg-red-900/30 dark:border-red-700' : 'border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400'}"
            autocomplete="off" spellcheck="false"
          />
          <button
            onclick={submitConnectGuess}
            class="px-4 py-2 text-sm font-medium bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors flex-shrink-0"
          >Guess</button>
          <button
            onclick={() => { connectRevealed = true; connectResult = null; }}
            class="px-3 py-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 font-medium transition-colors flex-shrink-0"
          >Reveal</button>
        </div>
        {#if connectResult === 'almost'}
          <p class="text-xs text-amber-600 dark:text-amber-400 mt-2">Close! Try again.</p>
        {:else if connectResult === 'wrong'}
          <p class="text-xs text-red-500 dark:text-red-400 mt-2">Not quite. Keep trying!</p>
        {/if}
      {/if}
    </div>
  {/if}

  <!-- Prev / Next session navigation -->
  <div class="flex justify-between pt-4 border-t border-gray-200 dark:border-gray-700 gap-4">
    {#if adj.next}
      <a href="/session/{adj.next.id}" class="flex items-center gap-2 text-sm text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group max-w-[45%]">
        <svg class="w-4 h-4 flex-shrink-0 group-hover:-translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        <div class="min-w-0">
          <p class="text-xs text-gray-400 dark:text-gray-500">Older</p>
          <p class="font-medium text-gray-700 dark:text-gray-300 group-hover:text-primary-600 truncate">{adj.next.quiz_type === 'connect' ? `${adj.next.quizmaster}'s Connect Quiz` : (adj.next.theme ?? `${adj.next.quizmaster}'s Quiz`)}</p>
        </div>
      </a>
    {:else}
      <div></div>
    {/if}

    {#if adj.prev}
      <a href="/session/{adj.prev.id}" class="flex items-center gap-2 text-sm text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group text-right max-w-[45%]">
        <div class="min-w-0">
          <p class="text-xs text-gray-400 dark:text-gray-500">Newer</p>
          <p class="font-medium text-gray-700 dark:text-gray-300 group-hover:text-primary-600 dark:group-hover:text-primary-400 truncate">{adj.prev.quiz_type === 'connect' ? `${adj.prev.quizmaster}'s Connect Quiz` : (adj.prev.theme ?? `${adj.prev.quizmaster}'s Quiz`)}</p>
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
