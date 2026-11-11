<script lang="ts">
  import BaseCalendar, { type Cell } from './BaseCalendar.svelte';

  interface DeckFile {
    label: string | null;
    rel_path: string | null;
    format: string;
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

  let {
    decks,
    onOpenSeries,
    onOpenStandalone,
  }: {
    decks: DecksManifest;
    onOpenSeries: (s: Series) => void;
    onOpenStandalone: (d: Standalone) => void;
  } = $props();

  type DeckDayItem = {
    key: string;
    label: string;
    sublabel: string;
    approx: boolean;
    colorClass: string;
    onSelect: () => void;
  };

  const DOT_COLORS = [
    'bg-indigo-500', 'bg-orange-500', 'bg-sky-500', 'bg-emerald-500',
    'bg-pink-500', 'bg-amber-500', 'bg-violet-500', 'bg-teal-500',
  ];
  function hashString(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = (hash << 5) - hash + str.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash);
  }
  function colorFor(id: string): string {
    return DOT_COLORS[hashString(id) % DOT_COLORS.length];
  }

  const activityByDate = $derived.by(() => {
    const map = new Map<string, DeckDayItem[]>();
    const push = (date: string, item: DeckDayItem) => {
      if (!map.has(date)) map.set(date, []);
      map.get(date)!.push(item);
    };

    for (const s of decks.series) {
      const color = colorFor(s.id);
      for (const r of s.rounds) {
        push(r.date, {
          key: `${s.id}-${r.round}`,
          label: `#${r.round} ${s.title}`,
          sublabel: r.host ?? '',
          approx: r.date_approx,
          colorClass: color,
          onSelect: () => onOpenSeries(s),
        });
      }
    }

    for (const d of decks.standalone) {
      push(d.date, {
        key: d.id,
        label: d.title,
        sublabel: d.host ?? '',
        approx: d.date_approx,
        colorClass: colorFor(d.id),
        onSelect: () => onOpenStandalone(d),
      });
    }

    return map;
  });

  const seriesLegend = $derived(
    decks.series.map(s => ({ title: s.title, colorClass: colorFor(s.id) }))
  );

  const initView = $derived.by(() => {
    const allDates = [...activityByDate.keys()].sort();
    const earliest = allDates.at(0) ?? new Date().toISOString().slice(0, 10);
    const latest = allDates.at(-1) ?? new Date().toISOString().slice(0, 10);
    return { earliest, latest };
  });

  const [initYear, initMonth] = initView.latest.split('-').map(Number);
  let year = $state(initYear);
  let month = $state(initMonth);

  const canGoPrev = $derived.by(() => {
    const [minY, minM] = initView.earliest.split('-').map(Number);
    return year > minY || (year === minY && month > minM);
  });
  const canGoNext = $derived.by(() => {
    const [maxY, maxM] = initView.latest.split('-').map(Number);
    return year < maxY || (year === maxY && month < maxM);
  });

  function prevMonth() {
    if (!canGoPrev) return;
    if (month === 1) { year--; month = 12; } else month--;
  }
  function nextMonth() {
    if (!canGoNext) return;
    if (month === 12) { year++; month = 1; } else month++;
  }

  // Day popover
  let popoverDate = $state<string | null>(null);
  let popoverTop = $state(0);
  let popoverLeft = $state(0);
  let hideTimer: ReturnType<typeof setTimeout> | null = null;

  function openPopover(e: MouseEvent, dateStr: string) {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    popoverDate = dateStr;
    popoverTop = rect.bottom + 4;
    popoverLeft = rect.left;
  }
  function scheduleClose() {
    hideTimer = setTimeout(() => { popoverDate = null; }, 150);
  }
  function cancelClose() {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
  }
</script>

{#if popoverDate}
  {@const items = activityByDate.get(popoverDate) ?? []}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed z-50 bg-ui-card border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl py-1.5 min-w-[200px] max-w-[280px]"
    style="top: {popoverTop}px; left: {popoverLeft}px;"
    onmouseenter={cancelClose}
    onmouseleave={scheduleClose}
  >
    <p class="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide px-3 pb-1">
      {items.length} session{items.length !== 1 ? 's' : ''} this day{items[0]?.approx ? ' (approx. date)' : ''}
    </p>
    {#each items as item (item.key)}
      <button
        onclick={() => { item.onSelect(); popoverDate = null; }}
        class="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors text-left"
      >
        <span class="w-2 h-2 rounded-full flex-shrink-0 {item.colorClass}"></span>
        <span class="min-w-0">
          <span class="block text-xs text-gray-700 dark:text-gray-300 leading-snug truncate">{item.label}</span>
          {#if item.sublabel}
            <span class="block text-[10px] text-gray-400 dark:text-gray-500 truncate">{item.sublabel}</span>
          {/if}
        </span>
      </button>
    {/each}
  </div>
{/if}

<BaseCalendar {year} {month} {canGoPrev} {canGoNext} {prevMonth} {nextMonth}>
  {#snippet dayContent(cell: Cell)}
    {@const items = activityByDate.get(cell.dateStr) ?? []}
    {@const hasItems = items.length > 0 && cell.inMonth}
    {@const shown = items.slice(0, 4)}
    {@const extra = items.length - shown.length}

    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      onmouseenter={(e) => { if (hasItems) openPopover(e, cell.dateStr); }}
      onmouseleave={scheduleClose}
      onclick={(e) => { if (hasItems) openPopover(e as unknown as MouseEvent, cell.dateStr); }}
      role={hasItems ? 'button' : undefined}
      tabindex={hasItems ? 0 : undefined}
      class="flex flex-col items-center py-0.5 px-0.5 rounded-lg transition-colors min-h-[38px]
        {hasItems ? 'cursor-pointer hover:bg-primary-50 dark:hover:bg-primary-900/20' : 'cursor-default'}
        {!cell.inMonth ? 'opacity-20' : ''}"
    >
      <span class="text-xs font-medium w-6 h-6 flex items-center justify-center rounded-full flex-shrink-0
        {hasItems ? 'text-gray-800 dark:text-gray-200 font-semibold' : 'text-gray-400 dark:text-gray-500'}">
        {cell.day}
      </span>
      {#if hasItems}
        <span class="flex items-center gap-0.5 flex-wrap justify-center mt-px px-0.5">
          {#each shown as item (item.key)}
            <span class="w-1.5 h-1.5 rounded-full {item.colorClass} {item.approx ? 'opacity-50' : ''}" title={item.label}></span>
          {/each}
          {#if extra > 0}
            <span class="text-[9px] text-gray-400 dark:text-gray-500 leading-none">+{extra}</span>
          {/if}
        </span>
      {/if}
    </div>
  {/snippet}

  {#snippet legend()}
    <div class="flex items-center gap-2.5 flex-wrap justify-center">
      {#each seriesLegend as s (s.title)}
        <span class="flex items-center gap-1">
          <span class="inline-block w-2 h-2 rounded-full {s.colorClass}"></span>
          <span class="text-[10px] text-gray-600 dark:text-gray-300">{s.title}</span>
        </span>
      {/each}
    </div>
  {/snippet}
</BaseCalendar>
