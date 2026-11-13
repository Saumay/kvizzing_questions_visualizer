<script lang="ts">
  import { getContext } from 'svelte';
  import { formatDate } from '$lib/utils/time';
  import { topicHex } from '$lib/utils/topicColors';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import TopicFilter from '$lib/components/TopicFilter.svelte';
  import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';

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
  const store = getContext<QuestionStore>('store');

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
  // Medium-dark, cool palette (blue/teal/indigo) — dark enough for white
  // text without a heavy black scrim, no warm peach/pink tones.
  const GRADIENTS: [string, string][] = [
    ['#2a6690', '#2f6b66'],
    ['#34507a', '#3a6b86'],
    ['#2d5f5c', '#2a4d73'],
    ['#3a5a8a', '#2f6e8f'],
    ['#355c82', '#3d7a6e'],
    ['#2f4f70', '#355f72'],
    ['#3c6186', '#2f5a6e'],
    ['#2a5a6e', '#34506f'],
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

  function darken(hex: string, amount: number): string {
    const n = parseInt(hex.slice(1), 16);
    const r = Math.round(((n >> 16) & 255) * (1 - amount));
    const g = Math.round(((n >> 8) & 255) * (1 - amount));
    const b = Math.round((n & 255) * (1 - amount));
    return `#${[r, g, b].map(x => x.toString(16).padStart(2, '0')).join('')}`;
  }

  // Blends a color toward its own gray (same perceived brightness, no hue)
  // so the topic color reads as a muted tint rather than a fully saturated
  // block — the raw topic hex is too vivid once it fills an entire card.
  function desaturate(hex: string, amount: number): string {
    const n = parseInt(hex.slice(1), 16);
    const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    const gray = 0.299 * r + 0.587 * g + 0.114 * b;
    const mr = Math.round(r + (gray - r) * amount);
    const mg = Math.round(g + (gray - g) * amount);
    const mb = Math.round(b + (gray - b) * amount);
    return `#${[mr, mg, mb].map(x => x.toString(16).padStart(2, '0')).join('')}`;
  }

  // Card color reflects what the quiz was actually about — its most common
  // topic across every question in the session(s) it covers — rather than
  // an arbitrary hash, so similar-themed quizzes read as similar colors.
  // Falls back to the old hash-based palette when there's no topic data
  // (e.g. a deck round whose questions haven't been imported yet).
  function dominantTopic(sessionIds: string[]): string | null {
    const counts = new Map<string, number>();
    for (const id of sessionIds) {
      for (const [topic, count] of sessionTopicCounts.get(id) ?? []) {
        if (topic === 'general') continue;
        counts.set(topic, (counts.get(topic) ?? 0) + count);
      }
    }
    if (counts.size === 0) return null;
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
  }

  function gradientForCard(sessionIds: string[], fallbackId: string): [string, string] {
    const topic = dominantTopic(sessionIds);
    if (!topic) return gradientFor(fallbackId);
    const hex = desaturate(topicHex(topic), 0.5);
    return [darken(hex, 0.35), darken(hex, 0.12)];
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

  // Real, topic/title-matched CC-licensed photo per series or standalone
  // deck, fetched by pipeline/utils/fetch_deck_stock_photos.py - replaced
  // the earlier AI-generated banners (images/decks/, generate_deck_banners.py)
  // as the only banner source. No existence check - a missing file just
  // renders nothing, leaving the gradient base visible underneath.
  function deckBannerUrl(id: string): string {
    return `/images/decks-stock/${id}.jpg`;
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
  let filterKind = $state<'all' | 'series' | 'standalone'>('all');
  let filterRecordingOnly = $state(false);
  let filterTopics = $state(new Set<string>());
  let dateFrom = $state('');
  let dateTo = $state('');

  function matchesDateRange(date: string): boolean {
    return (!dateFrom || date >= dateFrom) && (!dateTo || date <= dateTo);
  }

  function roundSessionId(seriesId: string, round: number): string {
    return `deck-${seriesId}-r${round}`;
  }
  function standaloneSessionId(id: string): string {
    return `deck-${id}`;
  }

  // Topics live on individual questions, not on the deck manifest, so build
  // a session ID → topic → question-count map once from the question store
  // rather than looking them up per round on every filter/color pass. The
  // counts (not just presence) are what let dominantTopic() below pick the
  // session's most common topic for its card color.
  const sessionTopicCounts = $derived.by(() => {
    const map = new Map<string, Map<string, number>>();
    for (const q of store.getQuestions()) {
      if (!q.session?.id) continue;
      const counts = map.get(q.session.id) ?? new Map<string, number>();
      for (const t of q.question.topics ?? []) {
        if (!t) continue;
        counts.set(t, (counts.get(t) ?? 0) + 1);
      }
      map.set(q.session.id, counts);
    }
    return map;
  });

  function matchesTopics(sessionId: string): boolean {
    if (filterTopics.size === 0) return true;
    const topics = sessionTopicCounts.get(sessionId);
    if (!topics) return false;
    return [...filterTopics].some(t => topics.has(t));
  }

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

  const filteredSeries = $derived.by(() => {
    if (filterKind === 'standalone') return [];
    return decks.series
      .map(s => ({
        ...s,
        rounds: s.rounds.filter(r =>
          matchesHost(r.host) &&
          matchesDateRange(r.date) &&
          (!filterRecordingOnly || hasRecording(r.files)) &&
          matchesTopics(roundSessionId(s.id, r.round)) &&
          (matchesSearch(s.title) || matchesSearch(r.title) || (r.host ? matchesSearch(r.host) : false))
        ),
      }))
      .filter(s => s.rounds.length > 0);
  });

  const filteredStandalone = $derived.by(() => {
    if (filterKind === 'series') return [];
    return decks.standalone
      .filter(d => matchesHost(d.host))
      .filter(d => matchesDateRange(d.date))
      .filter(d => !filterRecordingOnly || hasRecording(d.files))
      .filter(d => matchesTopics(standaloneSessionId(d.id)))
      .filter(d => matchesSearch(d.title) || (d.host ? matchesSearch(d.host) : false))
      .sort((a, b) => b.date.localeCompare(a.date));
  });

  const hasFilters = $derived(!!(
    search || filterHosts.size > 0 || filterKind !== 'all' || filterRecordingOnly || filterTopics.size > 0 || dateFrom || dateTo
  ));
  function clearFilters() {
    search = ''; filterHosts = new Set(); filterKind = 'all'; filterRecordingOnly = false; filterTopics = new Set(); dateFrom = ''; dateTo = '';
  }

  // Gauntlet is the flagship series — give it a hero banner instead of
  // sitting in the grid as just another tile. Falls back to the biggest
  // series if Gauntlet itself gets filtered out, so the hero slot never
  // just vanishes while a Gauntlet round is still actually in the results.
  const heroSeries = $derived.by(() => {
    if (filteredSeries.length === 0) return null;
    return filteredSeries.find(s => s.id === 'gauntlet')
      ?? [...filteredSeries].sort((a, b) => b.rounds.length - a.rounds.length)[0];
  });
  const restSeries = $derived(filteredSeries.filter(s => s.id !== heroSeries?.id));
  const heroLatestRound = $derived.by(() => {
    if (!heroSeries || heroSeries.rounds.length === 0) return null;
    return [...heroSeries.rounds].sort((a, b) => a.date.localeCompare(b.date)).at(-1)!;
  });

  let openSeries = $state<Series | null>(null);
  let openStandalone = $state<Standalone | null>(null);

  // Unified timeline: series (minus the hero) and standalone sessions as one
  // sortable/groupable list, each rendered as the same banner-style card.
  type TimelineCard = {
    id: string; kind: 'series' | 'standalone'; title: string; subtitle: string;
    badge: string; recording: boolean; count: number; latestDate: string;
    sessionIds: string[]; onSelect: () => void;
    host: string | null; questionCount: number | null;
  };

  // Total questions across a series' rounds, looked up via each round's
  // session (falls back to null for any round not yet imported).
  function seriesQuestionCount(sessionIds: string[]): number | null {
    let total = 0;
    let any = false;
    for (const sid of sessionIds) {
      const s = store.getSessionById(sid);
      if (s) { total += s.question_count; any = true; }
    }
    return any ? total : null;
  }

  const timelineCards = $derived.by((): TimelineCard[] => {
    const cards: TimelineCard[] = [];
    for (const s of restSeries) {
      const latest = [...s.rounds].sort((a, b) => a.date.localeCompare(b.date)).at(-1)!;
      const sessionIds = s.rounds.map(r => roundSessionId(s.id, r.round));
      const hosts = seriesHosts(s);
      cards.push({
        id: s.id, kind: 'series', title: s.title,
        subtitle: hosts.join(', ') || 'Various hosts',
        badge: `${s.rounds.length} session${s.rounds.length !== 1 ? 's' : ''}`,
        recording: seriesHasRecording(s),
        count: s.rounds.length,
        latestDate: latest.date,
        sessionIds,
        onSelect: () => openSeries = s,
        // Most series rotate hosts across rounds, so there's no single
        // quizmaster to show - but when every round shares the same host,
        // surface it like a standalone session does.
        host: hosts.length === 1 ? hosts[0] : null,
        questionCount: seriesQuestionCount(sessionIds),
      });
    }
    for (const d of filteredStandalone) {
      const single = d.files.length === 1 ? d.files[0] : null;
      const sessionId = standaloneSessionId(d.id);
      const session = store.getSessionById(sessionId);
      cards.push({
        id: d.id, kind: 'standalone', title: d.title,
        subtitle: `${d.host ? d.host + ' · ' : ''}${d.date_approx ? '~' : ''}${formatDate(d.date)}`,
        badge: single ? FORMAT_LABEL[single.format] : `${d.files.length} files`,
        recording: !single && hasRecording(d.files),
        count: 1,
        latestDate: d.date,
        sessionIds: [sessionId],
        onSelect: () => {
          if (single) { if (single.url) window.open(single.url, '_blank', 'noopener'); }
          else { openStandalone = d; }
        },
        host: session?.quizmaster ?? d.host,
        questionCount: session?.question_count ?? null,
      });
    }
    return cards;
  });

  let sortBy = $state<'recency' | 'count' | 'alpha'>('recency');

  const sortedTimelineCards = $derived.by(() => {
    const cards = [...timelineCards];
    if (sortBy === 'count') return cards.sort((a, b) => b.count - a.count || b.latestDate.localeCompare(a.latestDate));
    if (sortBy === 'alpha') return cards.sort((a, b) => a.title.localeCompare(b.title));
    return cards.sort((a, b) => b.latestDate.localeCompare(a.latestDate));
  });

  // Month-grouped headers only make sense when sorted chronologically —
  // other sort modes render as one flat list instead.
  const timelineGroups = $derived.by(() => {
    if (sortBy !== 'recency') return [{ label: null as string | null, cards: sortedTimelineCards }];
    const groups = new Map<string, TimelineCard[]>();
    for (const c of sortedTimelineCards) {
      const key = c.latestDate.slice(0, 7);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(c);
    }
    return [...groups.entries()].map(([key, cards]) => {
      const [y, m] = key.split('-').map(Number);
      return { label: `${MONTH_NAMES[m - 1]} ${y}`, cards };
    });
  });

  const MONTH_NAMES = ['January','February','March','April','May','June',
                       'July','August','September','October','November','December'];
  function monthGroups(rounds: Round[]): { label: string; rounds: Round[] }[] {
    const sorted = [...rounds].sort((a, b) => a.date.localeCompare(b.date) || a.round - b.round);
    const groups = new Map<string, Round[]>();
    for (const r of sorted) {
      const key = r.date.slice(0, 7); // YYYY-MM
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(r);
    }
    return [...groups.entries()].map(([key, groupRounds]) => {
      const [y, m] = key.split('-').map(Number);
      return { label: `${MONTH_NAMES[m - 1]} ${y}`, rounds: groupRounds };
    });
  }
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape') { openSeries = null; openStandalone = null; } }} />

<div class="space-y-6">
  <p class="text-xs text-gray-400 dark:text-gray-500">
    {allHosts.length} hosts &middot;
    <a href="https://onedrive.live.com/?id=46AC280CA35DB7D4%21scf07fa2a6ff247399c81052c3d69f428&cid=46AC280CA35DB7D4&redeem=aHR0cHM6Ly8xZHJ2Lm1zL2YvYy80NmFjMjgwY2EzNWRiN2Q0L0lnQXEtZ2ZQOG04NVI1eUJCU3c5YWZRb0FhVUx2UTJpTl9WMWVzSGxsMDduOGtFP2U9Mll3ZXlH" target="_blank" rel="noopener noreferrer" class="text-primary-500 dark:text-primary-400 hover:underline">recordings</a>
    &middot;
    <a href="https://drive.google.com/drive/folders/1jrW0WThbmlnprdGACSLaOmTpn8-SZcuc" target="_blank" rel="noopener noreferrer" class="text-primary-500 dark:text-primary-400 hover:underline">slides source</a>
  </p>

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

    <!-- Series / standalone toggle -->
    <div class="inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
      {#each [['all', 'All'], ['series', 'Series'], ['standalone', 'One-off']] as [value, label] (value)}
        <button
          onclick={() => filterKind = value as typeof filterKind}
          class="px-3 py-2 transition-colors {filterKind === value ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
        >
          {label}
        </button>
      {/each}
    </div>

    <!-- Recording only -->
    <button
      onclick={() => filterRecordingOnly = !filterRecordingOnly}
      class="inline-flex items-center gap-1.5 text-sm border rounded-lg px-3 py-2 transition-colors {filterRecordingOnly ? 'bg-primary-500 text-white border-primary-500' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
    >
      <span>🎥 Recorded</span>
    </button>

    <!-- Topics (multi-select) -->
    <TopicFilter bind:topics={filterTopics} />

    <!-- Date range -->
    <div class="flex items-center gap-1.5 text-sm">
      <input
        type="date"
        bind:value={dateFrom}
        class="border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900"
      />
      <span class="text-gray-400 dark:text-gray-500">&ndash;</span>
      <input
        type="date"
        bind:value={dateTo}
        class="border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900"
      />
    </div>

    <button
      onclick={clearFilters}
      class="text-sm text-primary-500 dark:text-primary-400 hover:text-primary-600 dark:hover:text-primary-300 {hasFilters ? '' : 'invisible pointer-events-none'}"
    >
      Clear
    </button>
  </div>

  <ActiveFilterChips bind:topics={filterTopics} />

  {#if filteredSeries.length === 0 && filteredStandalone.length === 0}
    <EmptyState emoji="📂" message="No sessions match your filters" onClear={clearFilters} />
  {:else}
    <!-- Hero: flagship series -->
    {#if heroSeries}
      <!-- Fixed, topic-independent gradient: this is the one flagship hero
           slot on the page, not a representative sample of topic diversity,
           and tying its color to whatever topic happens to dominate kept
           landing on an unwanted yellow/amber cast (history's brand color)
           no matter how much that was tuned down. -->
      {@const c1 = '#1e3a5f'}
      {@const c2 = '#0f1f33'}
      {@const imgUrl = deckBannerUrl(heroSeries.id)}
      {@const hosts = seriesHosts(heroSeries)}
      <button
        onclick={() => openSeries = heroSeries}
        class="tile-grain group relative w-full overflow-hidden rounded-2xl text-left ring-1 ring-black/10 dark:ring-white/10 shadow-lg hover:shadow-2xl transition-all focus:outline-none focus:ring-2 focus:ring-primary-400"
      >
        <div class="absolute inset-0" style="background: linear-gradient(135deg, {c1}, {c2})"></div>
        {#if imgUrl}
          <div class="absolute inset-0 bg-cover bg-center opacity-25 group-hover:opacity-88 transition-opacity duration-300" style="background-image: url('{imgUrl}');"></div>
        {/if}
        <div class="absolute inset-0 bg-gradient-to-t from-black/35 via-black/10 to-black/0"></div>
        <div class="absolute top-4 right-4 sm:top-5 sm:right-6 text-right" style="text-shadow: 0 1px 3px rgba(0,0,0,0.35);">
          <p class="text-2xl sm:text-3xl font-black text-white leading-none">{heroSeries.rounds.length}</p>
          <p class="text-[10px] text-white/70 uppercase tracking-wide mt-1">rounds</p>
        </div>
        <div class="relative p-6 sm:p-8 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-5 min-h-[180px] sm:min-h-[200px]" style="text-shadow: 0 1px 3px rgba(0,0,0,0.35);">
          <div class="min-w-0">
            <span class="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-amber-300 mb-2">
              ⭐ Flagship series
            </span>
            <div class="flex items-center gap-3">
              <span class="text-3xl sm:text-4xl flex-shrink-0">{emojiFor(heroSeries.title)}</span>
              <div class="min-w-0">
                <h2 class="text-xl sm:text-3xl font-black text-white leading-tight truncate">{heroSeries.title}</h2>
                <p class="text-sm sm:text-base font-medium text-white/85 mt-1 truncate">
                  {hosts.slice(0, 5).join(', ')}{hosts.length > 5 ? ` +${hosts.length - 5} more` : ''}
                </p>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-5 flex-shrink-0 self-start sm:self-end">
            {#if heroLatestRound}
              <div class="text-right hidden sm:block">
                <p class="text-xs text-white/85">Latest: #{heroLatestRound.round}</p>
                <p class="text-[11px] text-white/60 mt-0.5">{heroLatestRound.date_approx ? '~' : ''}{formatDate(heroLatestRound.date)}</p>
              </div>
            {/if}
            <svg class="w-6 h-6 text-white/70 group-hover:text-white group-hover:translate-x-1 transition-all flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </div>
      </button>
    {/if}

    <!-- Unified timeline: every other series + standalone, as banner cards -->
    {#if timelineCards.length > 0}
      <div>
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">All sessions</h2>
          <div class="inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-xs">
            {#each [['recency', 'Recent'], ['count', 'Most sessions'], ['alpha', 'A–Z']] as [value, label] (value)}
              <button
                onclick={() => sortBy = value as typeof sortBy}
                class="px-2.5 py-1.5 transition-colors {sortBy === value ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
              >
                {label}
              </button>
            {/each}
          </div>
        </div>
        <div class="space-y-6">
          {#each timelineGroups as group (group.label ?? 'flat')}
            <div>
              {#if group.label}
                <p class="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-2">{group.label}</p>
              {/if}
              <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {#each group.cards as card (card.id)}
                  {@const [c1, c2] = gradientForCard(card.sessionIds, card.id)}
                  {@const imgUrl = deckBannerUrl(card.id)}
                  <!-- svelte-ignore a11y_no_static_element_interactions -->
                  <!-- svelte-ignore a11y_click_events_have_key_events -->
                  <div
                    role="button"
                    tabindex="0"
                    onclick={(e) => { if (!(e.target as HTMLElement).closest('a,button,input')) card.onSelect(); }}
                    onkeydown={(e) => { if (e.key === 'Enter') card.onSelect(); }}
                    class="tile-grain group relative overflow-hidden text-left rounded-xl ring-1 ring-black/10 dark:ring-white/10 shadow-sm hover:shadow-lg transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-400 aspect-square flex flex-col"
                  >
                    <div class="absolute inset-0" style="background: linear-gradient(135deg, {c1}, {c2})"></div>
                    <div class="absolute inset-0 bg-cover bg-center opacity-30 group-hover:opacity-85 transition-opacity duration-300" style="background-image: url('{imgUrl}');"></div>
                    <div class="absolute inset-0 bg-gradient-to-t from-black/50 via-black/15 to-black/0"></div>
                    <div class="relative flex flex-col justify-between h-full p-3 sm:p-4" style="text-shadow: 0 1px 2px rgba(0,0,0,0.35);">
                      <div class="flex items-start justify-between gap-2">
                        <span class="text-xl sm:text-2xl flex-shrink-0">{emojiFor(card.title)}</span>
                        <div class="flex items-center gap-1.5 flex-shrink-0">
                          {#if card.recording}<span class="text-sm" title="Recording available">🎥</span>{/if}
                          {#if card.kind === 'series'}
                            <span class="text-sm sm:text-base font-extrabold text-white leading-none">{card.count} session{card.count !== 1 ? 's' : ''}</span>
                          {/if}
                        </div>
                      </div>
                      <div class="min-w-0">
                        <p class="text-sm sm:text-base font-bold text-white leading-tight line-clamp-2">{card.title}</p>
                        {#if card.kind === 'series'}
                          {#if card.questionCount}
                            <p class="mt-1 truncate text-[11px] sm:text-xs font-medium text-white/85">{card.questionCount} questions</p>
                          {/if}
                          {#if card.host}
                            <p class="text-[11px] sm:text-xs font-medium text-white/85 truncate">
                              {#if store.getMember(card.host)}<a href="/member/{card.host}" class="hover:underline">{card.host}</a>{:else}{card.host}{/if}
                            </p>
                          {/if}
                        {:else}
                          <p class="text-[11px] sm:text-xs font-medium text-white/85 mt-1 truncate">
                            {#if card.host}{#if store.getMember(card.host)}<a href="/member/{card.host}" class="hover:underline">{card.host}</a>{:else}{card.host}{/if}{:else}{card.badge}{/if}{card.questionCount ? ` · ${card.questionCount} questions` : ''}
                          </p>
                        {/if}
                      </div>
                    </div>
                  </div>
                {/each}
              </div>
            </div>
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
        {#each monthGroups(s.rounds) as group (group.label)}
          <p class="px-5 py-1.5 text-[11px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide bg-gray-50 dark:bg-gray-800/50 sticky top-0">
            {group.label}
          </p>
          {#each group.rounds as r}
            {@const single = r.files.length === 1 ? r.files[0] : null}
            <!-- Always a div, not an <a> - a round's host name below is a
                 real <a href="/member/..."> and anchors can't nest. Clicking
                 the single-file download still works via onclick, guarded
                 the same way as elsewhere so the host link's own click
                 doesn't also trigger it. -->
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div
              role={single ? 'button' : undefined}
              tabindex={single ? 0 : undefined}
              onclick={(e) => { if (single?.url && !(e.target as HTMLElement).closest('a,button,input')) window.open(single.url, '_blank', 'noopener'); }}
              onkeydown={(e) => { if (single?.url && e.key === 'Enter' && !(e.target as HTMLElement).closest('a,button,input')) window.open(single.url, '_blank', 'noopener'); }}
              class="flex items-center justify-between gap-4 px-5 py-3 transition-colors {single && !single.url ? 'opacity-60 pointer-events-none' : single ? 'cursor-pointer hover:bg-primary-50 dark:hover:bg-primary-900/20' : ''}"
            >
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                  <span class="text-gray-400 dark:text-gray-500">#{r.round}</span> {r.title}
                </p>
                <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  {#if r.host}{#if store.getMember(r.host)}<a href="/member/{r.host}" class="hover:underline">{r.host}</a>{:else}{r.host}{/if} &middot; {/if}{r.date_approx ? '~' : ''}{formatDate(r.date)}{#if roundSize(r.files) > 0} &middot; {formatBytes(roundSize(r.files))}{/if}
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
            </div>
          {/each}
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
