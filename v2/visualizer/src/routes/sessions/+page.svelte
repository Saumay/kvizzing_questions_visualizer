<script lang="ts">
  import { getContext, onMount } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { formatDateTz, formatTime } from '$lib/utils/time';
  import { SESSION_IMAGE_OPACITY } from '$lib/config/ui';
  import SearchInput from '$lib/components/SearchInput.svelte';
  import FiltersToggleButton from '$lib/components/FiltersToggleButton.svelte';
  import TagFilter from '$lib/components/TagFilter.svelte';
  import TopicFilter from '$lib/components/TopicFilter.svelte';
  import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';

  const store = getContext<QuestionStore>('store');
  const tzCtx = getContext<{ value: string }>('timezone');
  const sessions = store.getSessions();
  const sessionTs = store.getSessionEarliestTimestamps();

  function sessionDate(session: { id: string; date: string }): string {
    const ts = sessionTs.get(session.id);
    return formatDateTz(ts ?? session.date, tzCtx?.value ?? 'Europe/London');
  }

  const quizmasters = [...new Set(sessions.map(s => s.quizmaster))].sort();

  // Build per-session index of topics and tags from all questions
  const sessionTopics = new Map<string, Set<string>>();
  const sessionTags = new Map<string, Set<string>>();
  for (const q of store.getQuestions()) {
    const sid = q.session?.id;
    if (!sid) continue;
    if (!sessionTopics.has(sid)) sessionTopics.set(sid, new Set());
    if (!sessionTags.has(sid)) sessionTags.set(sid, new Set());
    for (const t of q.question.topics ?? []) sessionTopics.get(sid)!.add(t);
    for (const t of q.question.tags ?? []) sessionTags.get(sid)!.add(t);
  }

  // Tag frequency = number of sessions containing that tag
  const tagFreq = new Map<string, number>();
  for (const tags of sessionTags.values()) {
    for (const tag of tags) tagFreq.set(tag, (tagFreq.get(tag) ?? 0) + 1);
  }
  const allTags = [...tagFreq.entries()].sort((a, b) => b[1] - a[1]).map(([t]) => t);

  let hoveredSessionId = $state<string | null>(null);
  let isMobile = $state(false);
  let mobileFiltersOpen = $state(false);

  onMount(() => {
    const mq = window.matchMedia('(max-width: 1023px)');
    isMobile = mq.matches;
    mq.addEventListener('change', e => { isMobile = e.matches; });
  });

  const activeFilterCount = $derived(
    [filterQuizmaster].filter(Boolean).length +
    (filterConnect !== 'all' ? 1 : 0) +
    (sortBy !== 'newest' ? 1 : 0) +
    filterTags.size + filterTopics.size
  );

  let search = $state('');
  let filterQuizmaster = $state('');
  let filterConnect = $state<'all' | 'connect' | 'regular'>('all');
  let filterTopics = $state(new Set<string>());
  let filterTags = $state(new Set<string>());
  let sortBy = $state<'newest' | 'oldest' | 'most_questions'>('newest');


  const filtered = $derived.by(() => {
    let results = sessions.filter(s => {
      const q = search.trim().toLowerCase();
      const searchable = s.quiz_type === 'connect'
        ? s.quizmaster.toLowerCase()
        : (s.theme?.toLowerCase() ?? '') + ' ' + s.quizmaster.toLowerCase();
      if (q && !searchable.includes(q)) return false;
      if (filterQuizmaster && s.quizmaster !== filterQuizmaster) return false;
      if (filterConnect === 'connect' && s.quiz_type !== 'connect') return false;
      if (filterConnect === 'regular' && s.quiz_type === 'connect') return false;
      if (filterTopics.size > 0 && ![...filterTopics].some(t => sessionTopics.get(s.id)?.has(t))) return false;
      if (filterTags.size > 0 && ![...filterTags].every(t => sessionTags.get(s.id)?.has(t))) return false;
      return true;
    });

    if (sortBy === 'newest') results = [...results].sort((a, b) => b.date.localeCompare(a.date));
    else if (sortBy === 'oldest') results = [...results].sort((a, b) => a.date.localeCompare(b.date));
    else if (sortBy === 'most_questions') results = [...results].sort((a, b) => b.question_count - a.question_count);

    return results;
  });

  const hasFilters = $derived(search || filterQuizmaster || filterConnect !== 'all' || filterTopics.size > 0 || filterTags.size > 0 || sortBy !== 'newest');

  function clearFilters() {
    search = '';
    filterQuizmaster = '';
    filterConnect = 'all';
    filterTopics = new Set();
    filterTags = new Set();
    sortBy = 'newest';
  }
</script>

<div class="space-y-6">
  <!-- Search + filters -->
  <div class="space-y-3">
    <!-- Search + mobile filters toggle -->
    <div class="flex gap-2">
      <SearchInput bind:value={search} placeholder="Search by theme or quizmaster…" />
      <FiltersToggleButton bind:open={mobileFiltersOpen} count={activeFilterCount} />
    </div>

    <!-- Filters panel (always visible on desktop, toggled on mobile) -->
    <div class="{isMobile && !mobileFiltersOpen ? 'hidden' : 'space-y-3'}">
      <!-- Dropdowns -->
      <div class="grid grid-cols-2 gap-2 lg:flex lg:flex-wrap">
        <select bind:value={filterQuizmaster} class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600 lg:w-40">
          <option value="">All quizmasters</option>
          {#each quizmasters as qm}
            <option value={qm}>{qm}</option>
          {/each}
        </select>
        <select bind:value={sortBy} class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600 lg:w-40">
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="most_questions">Most questions</option>
        </select>
        <div class="col-span-2 lg:col-auto flex items-center rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm overflow-hidden flex-shrink-0">
          {#each [['all', 'All'], ['connect', 'Connect'], ['regular', 'Regular']] as [val, label]}
            <button
              onclick={() => filterConnect = val as typeof filterConnect}
              class="px-3 py-1.5 transition-colors {filterConnect === val ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'}"
            >{label}</button>
          {/each}
        </div>
      </div>

      <!-- Tag + Topic filters -->
      <div class="flex flex-wrap items-center gap-2">
        <TagFilter bind:tags={filterTags} {allTags} {tagFreq} />
        <TopicFilter bind:topics={filterTopics} />
      </div>
    </div>

    <!-- Active chips — always visible -->
    <ActiveFilterChips bind:tags={filterTags} bind:topics={filterTopics} hasFilters={!!hasFilters} onClear={clearFilters} />
  </div>

  <!-- Results count -->
  <p class="text-sm text-gray-500 dark:text-gray-400">
    {filtered.length} session{filtered.length !== 1 ? 's' : ''}
    {#if hasFilters}<span class="text-primary-500 font-medium"> (filtered)</span>{/if}
  </p>

  {#if sessions.length === 0}
    <div class="text-center py-20 text-gray-400">
      <div class="text-4xl mb-3">📅</div>
      <p class="font-medium">No sessions yet</p>
    </div>
  {:else if filtered.length === 0}
    <div class="text-center py-16 text-gray-400">
      <div class="text-4xl mb-3">🔍</div>
      <p class="font-medium">No sessions match your filters</p>
      <button onclick={clearFilters} class="mt-2 text-sm text-primary-500 hover:text-primary-600">Clear filters</button>
    </div>
  {:else}
    <div class="space-y-4">
      {#each filtered as session}
        <a
          href="/session/{session.id}"
          class="relative overflow-hidden block bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md hover:border-primary-200 transition-all p-5 group [transform:translateZ(0)]"
          onmouseenter={(e) => { hoveredSessionId = session.id; const bg = e.currentTarget.querySelector('.session-bg') as HTMLElement | null; if (bg) bg.style.opacity = String(SESSION_IMAGE_OPACITY.card.hover); }}
          onmouseleave={(e) => { hoveredSessionId = null; const bg = e.currentTarget.querySelector('.session-bg') as HTMLElement | null; if (bg) bg.style.opacity = String(SESSION_IMAGE_OPACITY.card.default); }}
        >
          <div
            class="session-bg absolute inset-0 bg-cover bg-center transition-opacity"
            style="background-image: url('{session.quiz_type === 'connect' ? '/images/connect-quiz-bg.png' : '/images/sessions/' + session.id + '.jpg'}'); opacity: {SESSION_IMAGE_OPACITY.card.default}"
          ></div>

          {#if session.quiz_type === 'connect'}
            <span class="absolute top-3 right-3 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-primary-500 text-white z-10">
              <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              Connect
            </span>
          {/if}

          <div class="relative flex items-start justify-between gap-4">
            <div class="flex-1 min-w-0">
              <!-- Title -->
              <div class="flex items-center gap-2 mb-1">
                <div class="w-8 h-8 rounded-lg bg-primary-500 flex items-center justify-center flex-shrink-0">
                  <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                </div>
                <div>
                  <h2 class="text-base font-semibold text-primary-700 dark:text-primary-200 group-hover:text-primary-800 dark:group-hover:text-primary-100 transition-colors">
                    {session.quiz_type === 'connect' ? `${session.quizmaster}'s Connect Quiz` : (session.theme ?? `${session.quizmaster}'s Quiz`)}
                  </h2>
                  <p class="text-xs text-gray-700 dark:text-gray-300">Hosted by {session.quizmaster} · {sessionDate(session)}</p>
                </div>
              </div>

              <!-- Stats row -->
              <div class="flex flex-wrap gap-4 mt-3 text-sm">
                <div class="flex items-center gap-1.5 text-gray-800 transition-colors {hoveredSessionId === session.id ? 'dark:text-white' : 'dark:text-gray-200'}">
                  <svg class="w-4 h-4 text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span class="font-medium">{session.question_count}</span>
                  <span class="transition-colors {hoveredSessionId === session.id ? 'text-gray-700 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'}">questions</span>
                </div>
                {#if session.participant_count > 0}
                  <div class="flex items-center gap-1.5 text-gray-800 transition-colors {hoveredSessionId === session.id ? 'dark:text-white' : 'dark:text-gray-200'}">
                    <svg class="w-4 h-4 text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    <span class="font-medium">{session.participant_count}</span>
                    <span class="transition-colors {hoveredSessionId === session.id ? 'text-gray-700 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'}">participants</span>
                  </div>
                {/if}
                {#if session.avg_time_to_answer_seconds}
                  <div class="flex items-center gap-1.5 text-gray-800 transition-colors {hoveredSessionId === session.id ? 'dark:text-white' : 'dark:text-gray-200'}">
                    <svg class="w-4 h-4 text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span class="font-medium">{formatTime(session.avg_time_to_answer_seconds)}</span>
                    <span class="transition-colors {hoveredSessionId === session.id ? 'text-gray-700 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'}">avg solve</span>
                  </div>
                {/if}
                {#if session.avg_wrong_attempts}
                  <div class="flex items-center gap-1.5 text-gray-800 transition-colors {hoveredSessionId === session.id ? 'dark:text-white' : 'dark:text-gray-200'}">
                    <svg class="w-4 h-4 text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    <span class="font-medium">{session.avg_wrong_attempts.toFixed(1)}</span>
                    <span class="transition-colors {hoveredSessionId === session.id ? 'text-gray-700 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'}">avg wrong</span>
                  </div>
                {/if}
              </div>
            </div>

            <div class="flex-shrink-0 text-gray-300 group-hover:text-primary-400 transition-colors">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </div>
        </a>
      {/each}
    </div>
  {/if}
</div>
