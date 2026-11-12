<script lang="ts">
  import { getContext } from 'svelte';
  import { goto } from '$app/navigation';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import type { Question } from '$lib/types';
  import { formatDateTz } from '$lib/utils/time';
  import { highlightSegments, scorePct } from '$lib/utils/dupChecker';

  interface Props {
    question: Question;
    score: number;
    matchedEntities: string[];
    // 'topic' gets blue/relevance-toned labels, anything else (the default
    // duplicate-check flow and the deck-upload report) gets red/amber
    // duplicate-toned labels.
    styleMode?: 'duplicate' | 'topic';
  }
  const { question, score, matchedEntities, styleMode = 'duplicate' }: Props = $props();

  const store = getContext<QuestionStore>('store');
  const tzCtx = getContext<{ value: string }>('timezone');

  let expanded = $state(false);

  const pct = $derived(scorePct(score));
  const questionSegments = $derived(highlightSegments(question.question.text, matchedEntities));
  const answerSegments = $derived(question.answer?.text ? highlightSegments(question.answer.text, matchedEntities) : null);

  function scoreLabel(p: number): string {
    if (styleMode === 'topic') {
      if (p >= 80) return 'Highly relevant';
      if (p >= 60) return 'Relevant';
      return 'Loosely related';
    }
    if (p >= 80) return 'Very likely a duplicate';
    if (p >= 60) return 'Similar theme';
    return 'Loosely related';
  }

  function scoreCls(p: number): string {
    if (styleMode === 'topic') {
      if (p >= 80) return 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-300';
      if (p >= 60) return 'bg-sky-50 text-sky-600 dark:bg-sky-900/30 dark:text-sky-300';
      return 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
    }
    if (p >= 80) return 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300';
    if (p >= 60) return 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300';
    return 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
  }

  // Where a question actually came from isn't obvious from its text alone,
  // so surface it explicitly rather than making the reader infer it.
  function sourceBadge(q: Question): { label: string; cls: string } {
    if (!q.session) {
      return { label: 'General question', cls: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300' };
    }
    const session = store.getSessionById(q.session.id);
    if (session?.is_live) {
      return { label: '⭐ Live quiz', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' };
    }
    return { label: 'Quiz session', cls: 'bg-sky-50 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300' };
  }

  const source = $derived(sourceBadge(question));
</script>

<div class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md hover:border-primary-200 transition-all p-4">
  <div class="flex items-start justify-between gap-3">
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-1.5 mb-1.5 flex-wrap">
        <span class="inline-block text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded {source.cls}">
          {source.label}
        </span>
        {#if question.session?.quiz_type === 'connect'}
          <span class="inline-block text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400">
            Connect round
          </span>
        {/if}
        {#if matchedEntities.length > 0}
          <span class="inline-block text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300" title="These terms from your query are literally present in this question, factored into the score above but not a confidence claim on their own.">
            Mentions: {matchedEntities.join(', ')}
          </span>
        {/if}
      </div>
      <button
        type="button"
        onclick={() => (expanded = !expanded)}
        class="text-left w-full text-sm text-gray-800 dark:text-gray-200 {expanded ? '' : 'line-clamp-3'}"
      >
        {#each questionSegments as seg}{#if seg.hl}<mark class="bg-green-200 dark:bg-green-700/60 text-inherit rounded px-0.5">{seg.text}</mark>{:else}{seg.text}{/if}{/each}
      </button>
      {#if answerSegments}
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1 {expanded ? '' : 'line-clamp-1'}">
          <span class="font-medium">Answer:</span> {#each answerSegments as seg}{#if seg.hl}<mark class="bg-green-200 dark:bg-green-700/60 text-inherit rounded px-0.5">{seg.text}</mark>{:else}{seg.text}{/if}{/each}
        </p>
      {/if}
      <button type="button" onclick={() => (expanded = !expanded)} class="text-xs text-primary-600 dark:text-primary-400 hover:underline font-medium mt-1">
        {expanded ? 'Show less' : 'Show more'}
      </button>
    </div>
    <span class="flex-shrink-0 text-xs font-semibold px-2 py-1 rounded-full {scoreCls(pct)}" title={scoreLabel(pct)}>
      {pct}%
    </span>
  </div>
  <p class="text-xs text-gray-500 dark:text-gray-400 mt-2 flex items-center flex-wrap gap-x-1">
    <span>{question.question.asker} &middot; {formatDateTz(question.date, tzCtx?.value ?? 'Europe/London')}</span>
    {#if question.session?.theme}<span>&middot; {question.session.theme}</span>{/if}
    <button
      onclick={() => goto(`/question/${question.id}`)}
      class="ml-auto text-primary-600 dark:text-primary-400 hover:underline font-medium"
    >
      View question →
    </button>
    {#if question.session}
      <button
        onclick={() => goto(`/session/${question.session!.id}`)}
        class="text-primary-600 dark:text-primary-400 hover:underline font-medium"
      >
        View session →
      </button>
    {/if}
  </p>
</div>
