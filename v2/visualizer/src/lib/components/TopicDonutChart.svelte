<script lang="ts">
  import { topicHex, topicLabel } from '$lib/utils/topicColors';

  type Row = { topic: string; count: number; pct: number };
  interface Props {
    rows: Row[]; // every topic, already sorted desc by count
    onTopicClick: (topic: string) => void;
  }
  const { rows, onTopicClick }: Props = $props();

  const total = $derived(rows.reduce((s, r) => s + r.count, 0) || 1);

  const CENTER = 100;
  const OUTER_R = 80;
  const INNER_R = 48;

  function polarToCartesian(r: number, angleDeg: number) {
    const rad = ((angleDeg - 90) * Math.PI) / 180;
    return { x: CENTER + r * Math.cos(rad), y: CENTER + r * Math.sin(rad) };
  }

  // Donut (not a full pie) so a slim slice for a rarely-asked topic doesn't
  // collapse to an unreadable point at the center the way a pie's would.
  function arcPath(startAngle: number, endAngle: number): string {
    const outerStart = polarToCartesian(OUTER_R, endAngle);
    const outerEnd = polarToCartesian(OUTER_R, startAngle);
    const innerStart = polarToCartesian(INNER_R, startAngle);
    const innerEnd = polarToCartesian(INNER_R, endAngle);
    const largeArc = endAngle - startAngle > 180 ? 1 : 0;
    return [
      `M ${outerStart.x} ${outerStart.y}`,
      `A ${OUTER_R} ${OUTER_R} 0 ${largeArc} 0 ${outerEnd.x} ${outerEnd.y}`,
      `L ${innerStart.x} ${innerStart.y}`,
      `A ${INNER_R} ${INNER_R} 0 ${largeArc} 1 ${innerEnd.x} ${innerEnd.y}`,
      'Z',
    ].join(' ');
  }

  const slices = $derived.by(() => {
    let angle = 0;
    return rows.map(r => {
      const sweep = (r.count / total) * 360;
      const slice = { ...r, startAngle: angle, endAngle: angle + sweep };
      angle += sweep;
      return slice;
    });
  });

  let hovered = $state<string | null>(null);
  function dim(topic: string): boolean {
    return hovered !== null && hovered !== topic;
  }
</script>

<div class="flex flex-col sm:flex-row items-center gap-6">
  <svg viewBox="0 0 200 200" class="w-44 h-44 flex-shrink-0">
    {#each slices as s (s.topic)}
      <path
        d={arcPath(s.startAngle, s.endAngle)}
        fill={topicHex(s.topic)}
        opacity={dim(s.topic) ? 0.35 : 1}
        class="cursor-pointer transition-opacity"
        role="button"
        tabindex="0"
        aria-label="{topicLabel(s.topic)}: {s.count} questions, {s.pct}%"
        onmouseenter={() => hovered = s.topic}
        onmouseleave={() => hovered = null}
        onclick={() => onTopicClick(s.topic)}
        onkeydown={(e) => { if (e.key === 'Enter') onTopicClick(s.topic); }}
      ><title>{topicLabel(s.topic)}: {s.count} ({s.pct}%)</title></path>
    {/each}
    <text x={CENTER} y={CENTER - 4} text-anchor="middle" class="fill-gray-900 dark:fill-white font-bold" style="font-size:22px;">{total}</text>
    <text x={CENTER} y={CENTER + 14} text-anchor="middle" class="fill-gray-400" style="font-size:10px;">questions</text>
  </svg>
  <div class="flex-1 min-w-0 grid grid-cols-2 gap-x-3 gap-y-1.5 w-full">
    {#each rows as r (r.topic)}
      <button
        type="button"
        onclick={() => onTopicClick(r.topic)}
        onmouseenter={() => hovered = r.topic}
        onmouseleave={() => hovered = null}
        class="flex items-center gap-1.5 text-left text-xs rounded px-1 py-0.5 hover:bg-gray-50 dark:hover:bg-gray-800/60 transition-colors transition-opacity {dim(r.topic) ? 'opacity-35' : ''}"
      >
        <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" style="background-color:{topicHex(r.topic)}"></span>
        <span class="truncate text-gray-700 dark:text-gray-300">{topicLabel(r.topic)}</span>
        <span class="text-gray-400 ml-auto flex-shrink-0">{r.count}</span>
      </button>
    {/each}
  </div>
</div>
