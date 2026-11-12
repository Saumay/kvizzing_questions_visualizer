<script lang="ts">
  // GitHub-style contribution heatmap: one cell per day over the trailing
  // `weeks` weeks, colored by that day's activity count. The color scale is
  // relative to this member's own busiest day (not a fixed absolute scale),
  // the same way GitHub's own heatmap scales per account, so a lighter user
  // still gets a readable gradient instead of every day looking equally faint.
  interface Props {
    dates: string[]; // YYYY-MM-DD occurrences; duplicates are counted
    weeks?: number;
  }
  const { dates, weeks = 53 }: Props = $props();

  type Cell = { key: string; date: Date; count: number; future: boolean };

  function toISODate(d: Date): string {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  const counts = $derived.by(() => {
    const m = new Map<string, number>();
    for (const d of dates) m.set(d, (m.get(d) ?? 0) + 1);
    return m;
  });

  const grid = $derived.by((): Cell[][] => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const endSunday = new Date(today);
    endSunday.setDate(today.getDate() - today.getDay());
    const start = new Date(endSunday);
    start.setDate(endSunday.getDate() - (weeks - 1) * 7);

    const cols: Cell[][] = [];
    for (let w = 0; w < weeks; w++) {
      const col: Cell[] = [];
      for (let d = 0; d < 7; d++) {
        const day = new Date(start);
        day.setDate(start.getDate() + w * 7 + d);
        const key = toISODate(day);
        col.push({ key, date: day, count: counts.get(key) ?? 0, future: day > today });
      }
      cols.push(col);
    }
    return cols;
  });

  const maxCount = $derived(Math.max(1, ...[...counts.values()]));

  function level(count: number): number {
    if (count === 0) return 0;
    const ratio = count / maxCount;
    if (ratio > 0.75) return 4;
    if (ratio > 0.5) return 3;
    if (ratio > 0.25) return 2;
    return 1;
  }

  const LEVEL_CLS = [
    'bg-gray-100 dark:bg-gray-800',
    'bg-primary-100 dark:bg-primary-900/50',
    'bg-primary-300 dark:bg-primary-700/70',
    'bg-primary-500 dark:bg-primary-500',
    'bg-primary-700 dark:bg-primary-300',
  ];

  const monthLabelByCol = $derived.by(() => {
    const labels = new Map<number, string>();
    let lastMonth = -1;
    grid.forEach((col, i) => {
      const m = col[0].date.getMonth();
      if (m !== lastMonth) {
        labels.set(i, col[0].date.toLocaleDateString('en-US', { month: 'short' }));
        lastMonth = m;
      }
    });
    return labels;
  });

  function tooltip(cell: Cell): string {
    const label = cell.date.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' });
    return `${cell.count} question${cell.count === 1 ? '' : 's'} — ${label}`;
  }
</script>

<div class="overflow-x-auto">
  <div class="inline-flex flex-col gap-1 min-w-full">
    <div class="flex gap-[3px]">
      {#each grid as _col, i}
        <div class="w-[11px] flex-shrink-0 relative h-3">
          {#if monthLabelByCol.has(i)}
            <span class="absolute left-0 top-0 text-[10px] text-gray-400 dark:text-gray-500 whitespace-nowrap">{monthLabelByCol.get(i)}</span>
          {/if}
        </div>
      {/each}
    </div>
    <div class="flex gap-[3px]">
      {#each grid as col}
        <div class="flex flex-col gap-[3px]">
          {#each col as cell (cell.key)}
            {#if cell.future}
              <div class="w-[11px] h-[11px]"></div>
            {:else}
              <button
                type="button"
                class="w-[11px] h-[11px] rounded-sm {LEVEL_CLS[level(cell.count)]} hover:ring-2 hover:ring-primary-400 focus-visible:ring-2 focus-visible:ring-primary-500 ring-offset-1 ring-offset-white dark:ring-offset-gray-900 transition-shadow"
                title={tooltip(cell)}
                aria-label={tooltip(cell)}
              ></button>
            {/if}
          {/each}
        </div>
      {/each}
    </div>
    <div class="flex items-center justify-end gap-1 pt-1 text-[10px] text-gray-400 dark:text-gray-500">
      <span>Less</span>
      {#each LEVEL_CLS as cls}
        <span class="w-[10px] h-[10px] rounded-sm {cls}"></span>
      {/each}
      <span>More</span>
    </div>
  </div>
</div>
