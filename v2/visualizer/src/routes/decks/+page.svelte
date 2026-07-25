<script lang="ts">
  import { formatDate } from '$lib/utils/time';
  import EmptyState from '$lib/components/EmptyState.svelte';

  interface DeckFile {
    label: string | null;
    rel_path: string | null;
    format: 'pdf' | 'pptx' | 'docx' | 'mp4' | 'vtt' | 'recording';
    r2_key: string | null;
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
    pdf: 'PDF', pptx: 'PPTX', docx: 'DOCX', mp4: 'MP4', vtt: 'VTT', recording: 'Video',
  };
  const FORMAT_CLS: Record<DeckFile['format'], string> = {
    pdf: 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300',
    pptx: 'bg-orange-50 text-orange-600 dark:bg-orange-900/30 dark:text-orange-300',
    docx: 'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300',
    mp4: 'bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-300',
    vtt: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
    recording: 'bg-rose-50 text-rose-600 dark:bg-rose-900/30 dark:text-rose-300',
  };

  // Deterministic cover-art gradient per card — cheap, no external image
  // generation (avoids the NSFW/moderation headaches of AI-generated covers).
  const GRADIENTS: [string, string][] = [
    ['#6366F1', '#8B5CF6'],
    ['#F97316', '#EF4444'],
    ['#0EA5E9', '#06B6D4'],
    ['#10B981', '#059669'],
    ['#EC4899', '#F43F5E'],
    ['#F59E0B', '#F97316'],
    ['#8B5CF6', '#6366F1'],
    ['#14B8A6', '#0EA5E9'],
  ];

  function hashString(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = (hash << 5) - hash + str.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash);
  }
  function gradientFor(id: string): [string, string] {
    return GRADIENTS[hashString(id) % GRADIENTS.length];
  }

  // Two soft glow blobs (one per gradient color) positioned deterministically
  // per card, on a near-black base — a "dark poster" look rather than a flat
  // color fill, with no external image asset needed.
  function glowsFor(id: string, c1: string, c2: string): { top: number; left: number; size: number; color: string }[] {
    const h = hashString(id);
    return [
      { top: -10 + (h % 30), left: 50 + ((h >> 4) % 40), size: 160 + (h % 60), color: c1 },
      { top: 40 + ((h >> 8) % 40), left: -15 + ((h >> 12) % 30), size: 130 + ((h >> 6) % 60), color: c2 },
    ];
  }

  function emojiFor(title: string): string {
    const t = title.toLowerCase();
    if (t.includes('gauntlet')) return '🥊';
    if (t.includes('krazzy')) return '🎪';
    if (t.includes('mtv') || t.includes('tournament')) return '🏆';
    if (t.includes('megakviz')) return '🧠';
    if (t.includes('movie') || t.includes('cinema')) return '🎬';
    if (t.includes('buzz')) return '🔔';
    if (t.includes('rewind') || t.includes('kvest')) return '🎉';
    if (t.includes('sport')) return '⚽';
    if (t.includes('bollywood')) return '🎭';
    if (t.includes('history')) return '🏛️';
    if (t.includes('animal') || t.includes('kvizimal')) return '🐾';
    if (t.includes('4th') || t.includes('space')) return '🚀';
    if (t.includes('visual')) return '🖼️';
    if (t.includes('swine') || t.includes('clue')) return '🕵️';
    return '🎯';
  }

  // PDF always renders last so it consistently lands in the same (rightmost)
  // slot whether or not a round has other formats alongside it.
  function withPdfLast(files: DeckFile[]): DeckFile[] {
    return [...files].sort((a, b) => (a.format === 'pdf' ? 1 : 0) - (b.format === 'pdf' ? 1 : 0));
  }

  function roundSize(files: DeckFile[]): number {
    return files.reduce((sum, f) => sum + f.size_bytes, 0);
  }
  function seriesHosts(s: Series): string[] {
    return [...new Set(s.rounds.map(r => r.host).filter((h): h is string => !!h))];
  }
  function hasRecording(files: DeckFile[]): boolean {
    return files.some(f => f.format === 'recording');
  }
  function seriesHasRecording(s: Series): boolean {
    return s.rounds.some(r => hasRecording(r.files));
  }

  // Opens every downloadable file in the group. Browsers only honor the
  // `download` attribute for same-origin URLs, and these are served from R2
  // (a different origin), so this opens each in a new tab rather than
  // silently saving — staggered slightly since firing many at once in the
  // same tick tends to trip popup blockers.
  function downloadAll(files: DeckFile[]) {
    const urls = withPdfLast(files).map(f => f.url).filter((u): u is string => !!u);
    urls.forEach((url, i) => {
      setTimeout(() => window.open(url, '_blank', 'noopener'), i * 250);
    });
  }

  let search = $state('');
  let filterHosts = $state(new Set<string>());
  let showHostMenu = $state(false);

  const allHosts = $derived.by(() => {
    const set = new Set<string>();
    for (const s of decks.series) for (const r of s.rounds) if (r.host) set.add(r.host);
    for (const d of decks.standalone) if (d.host) set.add(d.host);
    return [...set].sort();
  });

  function toggleHost(host: string) {
    const next = new Set(filterHosts);
    if (next.has(host)) next.delete(host); else next.add(host);
    filterHosts = next;
  }

  const hostLabel = $derived(
    filterHosts.size === 0 ? 'All hosts'
      : filterHosts.size === 1 ? [...filterHosts][0]
      : `${filterHosts.size} hosts`
  );

  function matchesHost(host: string | null): boolean {
    return filterHosts.size === 0 || (host !== null && filterHosts.has(host));
  }

  function matchesSearch(text: string): boolean {
    const q = search.trim().toLowerCase();
    return !q || text.toLowerCase().includes(q);
  }

  const filteredSeries = $derived.by(() =>
    decks.series
      .map(s => ({
        ...s,
        rounds: s.rounds.filter(r =>
          matchesHost(r.host) &&
          (matchesSearch(s.title) || matchesSearch(r.title) || (r.host ? matchesSearch(r.host) : false))
        ),
      }))
      .filter(s => s.rounds.length > 0)
  );

  const filteredStandalone = $derived.by(() =>
    decks.standalone
      .filter(d => matchesHost(d.host))
      .filter(d => matchesSearch(d.title) || (d.host ? matchesSearch(d.host) : false))
      .sort((a, b) => b.date.localeCompare(a.date))
  );

  const hasFilters = $derived(!!(search || filterHosts.size > 0));
  function clearFilters() { search = ''; filterHosts = new Set(); }

  const totalDecks = $derived(
    decks.series.reduce((n, s) => n + s.rounds.length, 0) + decks.standalone.length
  );

  let openSeries = $state<Series | null>(null);
  let openStandalone = $state<Standalone | null>(null);
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape') { openSeries = null; openStandalone = null; } }} />

<div class="space-y-6">
  <div>
    <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Live Sessions</h1>
    <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
      Live sessions are the best, here's every session from every hosted quiz night, fireside chat, slides and source files, ready to download.
    </p>
    <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
      {totalDecks} sessions &middot; {allHosts.length} hosts &middot;
      <a href="https://onedrive.live.com/?id=46AC280CA35DB7D4%21scf07fa2a6ff247399c81052c3d69f428&cid=46AC280CA35DB7D4&redeem=aHR0cHM6Ly8xZHJ2Lm1zL2YvYy80NmFjMjgwY2EzNWRiN2Q0L0lnQXEtZ2ZQOG04NVI1eUJCU3c5YWZRb0FhVUx2UTJpTl9WMWVzSGxsMDduOGtFP2U9Mll3ZXlH" target="_blank" rel="noopener noreferrer" class="text-primary-500 dark:text-primary-400 hover:underline">recordings</a>
      &middot;
      <a href="https://drive.google.com/drive/folders/1jrW0WThbmlnprdGACSLaOmTpn8-SZcuc" target="_blank" rel="noopener noreferrer" class="text-primary-500 dark:text-primary-400 hover:underline">slides source</a>
    </p>
  </div>

  <!-- Search + host filter -->
  <div class="flex flex-wrap items-center gap-2">
    <input
      type="text"
      bind:value={search}
      placeholder="Search sessions or hosts…"
      class="flex-1 min-w-[180px] text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900"
    />
    <div class="relative">
      <button
        onclick={() => showHostMenu = !showHostMenu}
        class="inline-flex items-center gap-1.5 text-sm border rounded-lg px-3 py-2 transition-colors {filterHosts.size > 0 ? 'bg-primary-500 text-white border-primary-500' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
      >
        <span>{hostLabel}</span>
        <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {#if showHostMenu}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div class="fixed inset-0 z-40" role="presentation" onclick={() => showHostMenu = false}></div>
        <div class="absolute left-0 top-full mt-1 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 py-1 w-56 max-h-72 overflow-y-auto">
          {#each allHosts as host (host)}
            <label class="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer">
              <input
                type="checkbox"
                checked={filterHosts.has(host)}
                onchange={() => toggleHost(host)}
                class="rounded border-gray-300 dark:border-gray-600 text-primary-500 focus:ring-1 focus:ring-primary-400"
              />
              <span class="truncate">{host}</span>
            </label>
          {/each}
        </div>
      {/if}
    </div>
    <button
      onclick={clearFilters}
      class="text-sm text-primary-500 dark:text-primary-400 hover:text-primary-600 dark:hover:text-primary-300 {hasFilters ? '' : 'invisible pointer-events-none'}"
    >
      Clear
    </button>
  </div>

  {#if filteredSeries.length === 0 && filteredStandalone.length === 0}
    <EmptyState emoji="📂" message="No sessions match your filters" onClear={clearFilters} />
  {:else}
    <!-- Series -->
    {#if filteredSeries.length > 0}
      <div>
        <h2 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">Series</h2>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {#each filteredSeries as s (s.id)}
            {@const [c1, c2] = gradientFor(s.id)}
            {@const glows = glowsFor(s.id, c1, c2)}
            <button
              onclick={() => openSeries = s}
              class="tile-grain group relative aspect-[4/3] rounded-2xl overflow-hidden text-left bg-gray-100 dark:bg-gray-950 ring-1 ring-gray-200 dark:ring-white/10 shadow-md hover:shadow-xl hover:ring-gray-300 dark:hover:ring-white/20 transition-all hover:-translate-y-1 focus:outline-none focus:ring-2 focus:ring-primary-400"
            >
              {#each glows as glow}
                <div
                  class="absolute rounded-full blur-3xl pointer-events-none transition-transform duration-500 group-hover:scale-110"
                  style="top: {glow.top}%; left: {glow.left}%; width: {glow.size}px; height: {glow.size}px; background: {glow.color}; opacity: 0.55"
                ></div>
              {/each}
              <div class="absolute inset-0 bg-gradient-to-t from-white/85 dark:from-black/80 via-white/25 dark:via-black/20 to-white/5 dark:to-black/10"></div>
              <span class="absolute top-2.5 right-2.5 inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full bg-black/10 dark:bg-white/10 backdrop-blur-md ring-1 ring-black/10 dark:ring-white/10 text-gray-800 dark:text-white/90">
                {#if seriesHasRecording(s)}<span title="Recording available">🎥</span>{/if}
                {s.rounds.length} session{s.rounds.length !== 1 ? 's' : ''}
              </span>
              <span
                class="absolute top-2.5 left-2.5 w-10 h-10 rounded-xl bg-black/5 dark:bg-white/10 backdrop-blur-md ring-1 ring-black/10 dark:ring-white/10 flex items-center justify-center text-xl"
                style="box-shadow: 0 0 22px {c1}66"
              >{emojiFor(s.title)}</span>
              <div class="absolute bottom-0 inset-x-0 p-3">
                <p class="text-base font-bold text-gray-900 dark:text-white leading-tight line-clamp-2">{s.title}</p>
                <p class="text-[11px] text-gray-600 dark:text-white/65 mt-0.5 truncate">{seriesHosts(s).join(', ') || 'Various hosts'}</p>
              </div>
            </button>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Standalone -->
    {#if filteredStandalone.length > 0}
      <div>
        <h2 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">One-off sessions</h2>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {#each filteredStandalone as d (d.id)}
            {@const [c1, c2] = gradientFor(d.id)}
            {@const glows = glowsFor(d.id, c1, c2)}
            {@const single = d.files.length === 1 ? d.files[0] : null}
            <svelte:element
              this={single ? 'a' : 'button'}
              href={single ? (single.url ?? undefined) : undefined}
              target={single ? '_blank' : undefined}
              rel={single ? 'noopener noreferrer' : undefined}
              role={single ? undefined : 'button'}
              tabindex={single ? undefined : 0}
              onclick={single ? undefined : () => openStandalone = d}
              class="tile-grain group relative aspect-[4/3] rounded-2xl overflow-hidden text-left bg-gray-100 dark:bg-gray-950 ring-1 ring-gray-200 dark:ring-white/10 shadow-md hover:shadow-xl hover:ring-gray-300 dark:hover:ring-white/20 transition-all hover:-translate-y-1 focus:outline-none focus:ring-2 focus:ring-primary-400 {single && !single.url ? 'pointer-events-none' : ''}"
            >
              {#each glows as glow}
                <div
                  class="absolute rounded-full blur-3xl pointer-events-none transition-transform duration-500 group-hover:scale-110"
                  style="top: {glow.top}%; left: {glow.left}%; width: {glow.size}px; height: {glow.size}px; background: {glow.color}; opacity: 0.55"
                ></div>
              {/each}
              <div class="absolute inset-0 bg-gradient-to-t from-white/85 dark:from-black/80 via-white/25 dark:via-black/20 to-white/5 dark:to-black/10"></div>
              <span class="absolute top-2.5 right-2.5 inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full bg-black/10 dark:bg-white/10 backdrop-blur-md ring-1 ring-black/10 dark:ring-white/10 text-gray-800 dark:text-white/90">
                {#if !single && hasRecording(d.files)}<span title="Recording available">🎥</span>{/if}
                {single ? FORMAT_LABEL[single.format] : `${d.files.length} files`}
              </span>
              <span
                class="absolute top-2.5 left-2.5 w-10 h-10 rounded-xl bg-black/5 dark:bg-white/10 backdrop-blur-md ring-1 ring-black/10 dark:ring-white/10 flex items-center justify-center text-xl"
                style="box-shadow: 0 0 22px {c1}66"
              >{emojiFor(d.title)}</span>
              <div class="absolute bottom-0 inset-x-0 p-3">
                <p class="text-base font-bold text-gray-900 dark:text-white leading-tight line-clamp-2">{d.title}</p>
                <p class="text-[11px] text-gray-600 dark:text-white/65 mt-0.5 truncate">
                  {#if d.host}{d.host} &middot; {/if}{d.date_approx ? '~' : ''}{formatDate(d.date)}
                </p>
              </div>
              {#if single && !single.url}
                <div class="absolute inset-0 flex items-center justify-center bg-white/70 dark:bg-black/60">
                  <span class="text-[10px] font-semibold text-gray-800 dark:text-white bg-white/70 dark:bg-black/50 px-2 py-1 rounded-full">Upload pending</span>
                </div>
              {/if}
            </svelte:element>
          {/each}
        </div>
      </div>
    {/if}
  {/if}
</div>

<!-- Series detail modal -->
{#if openSeries}
  {@const s = openSeries}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
    onclick={(e) => { if (e.target === e.currentTarget) openSeries = null; }}
  >
    <div class="bg-ui-card rounded-2xl shadow-xl w-full max-w-lg max-h-[85vh] overflow-hidden flex flex-col">
      <div class="p-5 pb-3 border-b border-gray-100 dark:border-gray-700 flex items-start justify-between gap-3 flex-shrink-0">
        <div class="min-w-0">
          <h2 class="text-lg font-bold text-gray-900 dark:text-gray-100 truncate">{s.title}</h2>
          {#if s.description}
            <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{s.description}</p>
          {/if}
        </div>
        <div class="flex-shrink-0 flex items-center gap-1">
          <button
            onclick={() => downloadAll(s.rounds.flatMap(r => r.files))}
            class="p-1.5 rounded-lg text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            title="Download all sessions"
            aria-label="Download all sessions"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </button>
          <button
            onclick={() => openSeries = null}
            class="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Close"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
      <div class="overflow-y-auto divide-y divide-gray-100 dark:divide-gray-700">
        {#each s.rounds as r}
          {@const single = r.files.length === 1 ? r.files[0] : null}
          <svelte:element
            this={single ? 'a' : 'div'}
            href={single ? (single.url ?? undefined) : undefined}
            target={single ? '_blank' : undefined}
            rel={single ? 'noopener noreferrer' : undefined}
            class="flex items-center justify-between gap-4 px-5 py-3 transition-colors {single && !single.url ? 'opacity-60 pointer-events-none' : 'hover:bg-primary-50 dark:hover:bg-primary-900/20'}"
          >
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                <span class="text-gray-400 dark:text-gray-500">#{r.round}</span> {r.title}
              </p>
              <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                {#if r.host}{r.host} &middot; {/if}{r.date_approx ? '~' : ''}{formatDate(r.date)}{#if roundSize(r.files) > 0} &middot; {formatBytes(roundSize(r.files))}{/if}
              </p>
            </div>
            <div class="flex-shrink-0 flex items-center gap-1.5 flex-wrap justify-end">
              {#each withPdfLast(r.files) as f}
                {#if single}
                  <!-- Row itself is the link; badge is decorative only -->
                  <span
                    class="inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-md {f.url ? FORMAT_CLS[f.format] : 'bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500'}"
                  >
                    {FORMAT_LABEL[f.format]}
                  </span>
                {:else if f.url}
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
          </svelte:element>
        {/each}
      </div>
    </div>
  </div>
{/if}

<!-- Standalone (multi-file) detail modal -->
{#if openStandalone}
  {@const d = openStandalone}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
    onclick={(e) => { if (e.target === e.currentTarget) openStandalone = null; }}
  >
    <div class="bg-ui-card rounded-2xl shadow-xl w-full max-w-sm overflow-hidden">
      <div class="p-5 pb-3 border-b border-gray-100 dark:border-gray-700 flex items-start justify-between gap-3">
        <div class="min-w-0">
          <h2 class="text-lg font-bold text-gray-900 dark:text-gray-100 truncate">{d.title}</h2>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {#if d.host}{d.host} &middot; {/if}{d.date_approx ? '~' : ''}{formatDate(d.date)}
          </p>
        </div>
        <div class="flex-shrink-0 flex items-center gap-1">
          <button
            onclick={() => downloadAll(d.files)}
            class="p-1.5 rounded-lg text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            title="Download all"
            aria-label="Download all"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </button>
        <button
          onclick={() => openStandalone = null}
          class="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          aria-label="Close"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
        </div>
      </div>
      <div class="p-5 pt-3 flex flex-wrap gap-2">
        {#each withPdfLast(d.files) as f}
          {#if f.url}
            <a
              href={f.url}
              target="_blank" rel="noopener noreferrer"
              class="inline-flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-md {FORMAT_CLS[f.format]} hover:opacity-80 transition-opacity"
            >
              {f.label ?? FORMAT_LABEL[f.format]}{#if f.size_bytes > 0} &middot; {formatBytes(f.size_bytes)}{/if}
            </a>
          {:else}
            <span
              class="inline-flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-md bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500 cursor-not-allowed"
              title="Upload pending"
            >
              {f.label ?? FORMAT_LABEL[f.format]}
            </span>
          {/if}
        {/each}
      </div>
    </div>
  </div>
{/if}

<style>
  /* Subtle grain over the dark tile glows — flat gradients read cheap,
     a touch of noise reads premium (same trick Stripe/Linear use). */
  .tile-grain::after {
    content: '';
    position: absolute;
    inset: 0;
    pointer-events: none;
    mix-blend-mode: overlay;
    opacity: 0.5;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  }
</style>
