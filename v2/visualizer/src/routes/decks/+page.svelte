<script lang="ts">
  import { formatDate } from '$lib/utils/time';
  import EmptyState from '$lib/components/EmptyState.svelte';

  interface DeckFile {
    label: string | null;
    rel_path: string;
    format: 'pdf' | 'pptx' | 'docx' | 'mp4' | 'vtt';
    r2_key: string;
    url: string | null;
    size_bytes: number;
  }
  interface Round {
    round: number;
    title: string;
    host: string | null;
    date: string;
    date_approx: boolean;
    files: DeckFile[];
  }
  interface Series {
    id: string;
    title: string;
    description: string | null;
    rounds: Round[];
  }
  interface Standalone {
    id: string;
    title: string;
    host: string | null;
    date: string;
    date_approx: boolean;
    files: DeckFile[];
  }
  interface DecksManifest {
    series: Series[];
    standalone: Standalone[];
    total_bytes: number;
  }

  let { data } = $props();
  const decks = data.decks as DecksManifest;

  function formatBytes(n: number): string {
    if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
    return `${(n / 1024 ** 2).toFixed(1)} MB`;
  }

  const FORMAT_LABEL: Record<DeckFile['format'], string> = {
    pdf: 'PDF', pptx: 'PPTX', docx: 'DOCX', mp4: 'MP4', vtt: 'VTT',
  };
  const FORMAT_CLS: Record<DeckFile['format'], string> = {
    pdf: 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300',
    pptx: 'bg-orange-50 text-orange-600 dark:bg-orange-900/30 dark:text-orange-300',
    docx: 'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300',
    mp4: 'bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-300',
    vtt: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
  };

  function roundSize(files: DeckFile[]): number {
    return files.reduce((sum, f) => sum + f.size_bytes, 0);
  }
  function seriesSize(s: Series): number {
    return s.rounds.reduce((sum, r) => sum + roundSize(r.files), 0);
  }
  function seriesHosts(s: Series): string[] {
    return [...new Set(s.rounds.map(r => r.host).filter((h): h is string => !!h))];
  }
  function seriesLatestDate(s: Series): string {
    return s.rounds.reduce((max, r) => (r.date > max ? r.date : max), s.rounds[0]?.date ?? '');
  }

  let search = $state('');
  let filterHost = $state('');

  const allHosts = $derived.by(() => {
    const set = new Set<string>();
    for (const s of decks.series) for (const r of s.rounds) if (r.host) set.add(r.host);
    for (const d of decks.standalone) if (d.host) set.add(d.host);
    return [...set].sort();
  });

  function matchesSearch(text: string): boolean {
    const q = search.trim().toLowerCase();
    return !q || text.toLowerCase().includes(q);
  }

  const filteredSeries = $derived.by(() =>
    decks.series
      .map(s => ({
        ...s,
        rounds: s.rounds.filter(r =>
          (!filterHost || r.host === filterHost) &&
          (matchesSearch(s.title) || matchesSearch(r.title) || (r.host ? matchesSearch(r.host) : false))
        ),
      }))
      .filter(s => s.rounds.length > 0)
  );

  const filteredStandalone = $derived.by(() =>
    decks.standalone
      .filter(d => !filterHost || d.host === filterHost)
      .filter(d => matchesSearch(d.title) || (d.host ? matchesSearch(d.host) : false))
      .sort((a, b) => b.date.localeCompare(a.date))
  );

  const hasFilters = $derived(!!(search || filterHost));
  function clearFilters() { search = ''; filterHost = ''; }

  let expanded = $state(new Set<string>());
  function toggle(id: string) {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id); else next.add(id);
    expanded = next;
  }

  const totalDecks = $derived(
    decks.series.reduce((n, s) => n + s.rounds.length, 0) + decks.standalone.length
  );
</script>

<div class="space-y-6">
  <div>
    <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Quiz Decks</h1>
    <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
      Presentation decks from hosted quiz nights &mdash; download the slides, source files, or recordings.
      {totalDecks} decks &middot; {formatBytes(decks.total_bytes)} total.
    </p>
  </div>

  <!-- Search + host filter -->
  <div class="flex flex-wrap items-center gap-2">
    <input
      type="text"
      bind:value={search}
      placeholder="Search decks or hosts…"
      class="flex-1 min-w-[180px] text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900"
    />
    <select
      bind:value={filterHost}
      class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
    >
      <option value="">All hosts</option>
      {#each allHosts as host}
        <option value={host}>{host}</option>
      {/each}
    </select>
    {#if hasFilters}
      <button onclick={clearFilters} class="text-sm text-primary-500 dark:text-primary-400 hover:text-primary-600 dark:hover:text-primary-300">
        Clear
      </button>
    {/if}
  </div>

  {#if filteredSeries.length === 0 && filteredStandalone.length === 0}
    <EmptyState emoji="📂" message="No decks match your filters" onClear={clearFilters} />
  {:else}
    <!-- Series -->
    {#if filteredSeries.length > 0}
      <div class="space-y-3">
        {#each filteredSeries as s (s.id)}
          {@const isOpen = expanded.has(s.id)}
          <div class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
            <button
              onclick={() => toggle(s.id)}
              class="w-full flex items-center justify-between gap-4 p-4 text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <h2 class="text-base font-semibold text-primary-700 dark:text-primary-200">{s.title}</h2>
                  <span class="text-xs text-gray-400 dark:text-gray-500">{s.rounds.length} round{s.rounds.length !== 1 ? 's' : ''}</span>
                </div>
                {#if s.description}
                  <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{s.description}</p>
                {/if}
                <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {#if seriesHosts(s).length > 0}{seriesHosts(s).join(', ')} &middot; {/if}
                  {formatDate(seriesLatestDate(s))} &middot; {formatBytes(seriesSize(s))}
                </p>
              </div>
              <svg
                class="w-5 h-5 flex-shrink-0 text-gray-400 transition-transform {isOpen ? 'rotate-180' : ''}"
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {#if isOpen}
              <div class="border-t border-gray-100 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700">
                {#each s.rounds as r}
                  <div class="flex items-center justify-between gap-4 px-4 py-3">
                    <div class="flex-1 min-w-0">
                      <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                        <span class="text-gray-400 dark:text-gray-500">#{r.round}</span> {r.title}
                      </p>
                      <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        {#if r.host}{r.host} &middot; {/if}{r.date_approx ? '~' : ''}{formatDate(r.date)}
                      </p>
                    </div>
                    <div class="flex-shrink-0 flex items-center gap-1.5 flex-wrap justify-end">
                      {#each r.files as f}
                        {#if f.url}
                          <a
                            href={f.url}
                            target="_blank" rel="noopener noreferrer"
                            class="inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-md {FORMAT_CLS[f.format]} hover:opacity-80 transition-opacity"
                            title={f.label ?? FORMAT_LABEL[f.format]}
                          >
                            {FORMAT_LABEL[f.format]}
                          </a>
                        {:else}
                          <span
                            class="inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-md bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500 cursor-not-allowed"
                            title="Upload pending"
                          >
                            {FORMAT_LABEL[f.format]}
                          </span>
                        {/if}
                      {/each}
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}

    <!-- Standalone -->
    {#if filteredStandalone.length > 0}
      <div>
        <h2 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">Other decks</h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {#each filteredStandalone as d (d.id)}
            <div class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-4">
              <p class="text-sm font-semibold text-gray-800 dark:text-gray-200 truncate">{d.title}</p>
              <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                {#if d.host}{d.host} &middot; {/if}{d.date_approx ? '~' : ''}{formatDate(d.date)}
              </p>
              <div class="flex items-center gap-1.5 flex-wrap mt-3">
                {#each d.files as f}
                  {#if f.url}
                    <a
                      href={f.url}
                      target="_blank" rel="noopener noreferrer"
                      class="inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-md {FORMAT_CLS[f.format]} hover:opacity-80 transition-opacity"
                    >
                      {FORMAT_LABEL[f.format]} &middot; {formatBytes(f.size_bytes)}
                    </a>
                  {:else}
                    <span
                      class="inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-md bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500 cursor-not-allowed"
                      title="Upload pending"
                    >
                      {FORMAT_LABEL[f.format]} &middot; {formatBytes(f.size_bytes)}
                    </span>
                  {/if}
                {/each}
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  {/if}
</div>
