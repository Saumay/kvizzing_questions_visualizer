<script lang="ts">
  import { getContext, onMount } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { createDupChecker, type DupMatch } from '$lib/utils/dupChecker';
  import DeckUpload from './DeckUpload.svelte';
  import ResultCard from './ResultCard.svelte';

  const store = getContext<QuestionStore>('store');

  const checker = createDupChecker(store);

  type Mode = 'duplicate' | 'topic' | 'deck';
  let mode = $state<Mode>('duplicate');

  const MODE_COPY: Record<'duplicate' | 'topic', { title: string; description: string; placeholder: string; cta: string; resultsHeading: string }> = {
    duplicate: {
      title: 'Check for Duplicates',
      description: "Paste your draft question and search the full question bank for similar ones already asked, catching reworded repeats, not just exact-text matches. Everything runs in your browser, so your question is never sent anywhere or seen by anyone else.",
      placeholder: 'e.g. "This Mughal emperor commissioned a mausoleum in Agra for his wife Mumtaz Mahal, completed around 1653 in white marble inlaid with precious stones. Name the emperor and the monument."',
      cta: 'Check for duplicates',
      resultsHeading: 'Closest matches',
    },
    topic: {
      title: 'Search by Topic',
      description: "Describe what you're looking for in plain language, like a person, event, or theme, and surface existing questions about it, however they were actually worded. Same engine as duplicate-check, read as \"what's been asked about X\" instead of an exact-match check.",
      placeholder: 'e.g. "questions about Shah Jahan" or "anything about 90s Bollywood music"…',
      cta: 'Search',
      resultsHeading: 'Related questions',
    },
  };

  let draft = $state('');
  // A lone name or a couple of words gives the embedding model nothing to
  // disambiguate with (e.g. "Shah Jahan" alone can match a Bollywood-cast
  // question just because it shares a similar name shape). Full sentences
  // work far better, so nudge toward that instead of silently returning
  // weak matches.
  const draftWordCount = $derived(draft.trim() ? draft.trim().split(/\s+/).length : 0);
  const isShortDraft = $derived(draftWordCount > 0 && draftWordCount < 6);
  let status = $state<'idle' | 'loading-model' | 'loading-corpus' | 'searching' | 'done' | 'error'>('idle');
  let errorMessage = $state('');
  let results = $state<DupMatch[]>([]);

  type IndexStatus = { ok: boolean; corpus_count: number | null; total_questions: number | null; last_success: string | null };
  let indexStatus = $state<IndexStatus | null>(null);

  onMount(async () => {
    try {
      const r = await fetch('/data/question_embeddings_status.json');
      if (r.ok) indexStatus = await r.json();
    } catch {
      // Best-effort: the page still works without this, it just won't show a freshness line.
    }
  });

  async function runSearch() {
    const text = draft.trim();
    if (!text) return;
    errorMessage = '';
    results = [];
    try {
      status = 'loading-model';
      await checker.ensureModelLoaded();
      status = 'loading-corpus';
      await checker.ensureCorpusLoaded();
      status = 'searching';
      results = await checker.search(text, 10);
      status = 'done';
    } catch (e) {
      console.error(e);
      errorMessage = e instanceof Error ? e.message : 'Something went wrong.';
      status = 'error';
    }
  }

  function switchMode(next: Mode) {
    if (mode === next) return;
    mode = next;
    results = [];
    status = 'idle';
    errorMessage = '';
  }
</script>

<div class="space-y-6 max-w-4xl">
  <div>
    <div class="flex items-center gap-3 flex-wrap">
      <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">
        {mode === 'deck' ? 'Check a Presentation for Duplicates' : MODE_COPY[mode].title}
      </h1>
      <div class="inline-flex items-center rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm overflow-hidden">
        <button
          onclick={() => switchMode('duplicate')}
          class="px-3 py-1.5 transition-colors {mode === 'duplicate' ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'}"
        >Check duplicates</button>
        <button
          onclick={() => switchMode('topic')}
          class="px-3 py-1.5 transition-colors border-l border-gray-200 dark:border-gray-600 {mode === 'topic' ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'}"
        >Search by topic</button>
        <button
          onclick={() => switchMode('deck')}
          class="px-3 py-1.5 transition-colors border-l border-gray-200 dark:border-gray-600 {mode === 'deck' ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'}"
        >Upload deck</button>
      </div>
    </div>
    {#if mode === 'deck'}
      <p class="text-sm text-gray-500 dark:text-gray-400 mt-2">
        Upload a quiz presentation (.pptx or .pdf) and check every slide against the full question bank at once. Everything runs in your browser, nothing is uploaded anywhere.
      </p>
    {:else}
      <p class="text-sm text-gray-500 dark:text-gray-400 mt-2">
        {MODE_COPY[mode].description}
      </p>
    {/if}
    {#if indexStatus}
      <p class="text-xs mt-2 flex items-center gap-1.5 {indexStatus.ok && indexStatus.corpus_count === indexStatus.total_questions ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'}">
        {#if indexStatus.ok && indexStatus.corpus_count === indexStatus.total_questions}
          ✓ Index up to date, covers all {indexStatus.total_questions?.toLocaleString()} questions
        {:else if indexStatus.corpus_count !== null && indexStatus.total_questions !== null}
          ⚠ Index covers {indexStatus.corpus_count.toLocaleString()} of {indexStatus.total_questions.toLocaleString()} questions, may be stale
        {:else}
          ⚠ Index status unavailable
        {/if}
      </p>
    {/if}
  </div>

  {#if mode === 'deck'}
    <DeckUpload {checker} />
  {:else}
    <div class="space-y-3">
      <textarea
        bind:value={draft}
        rows="8"
        placeholder={MODE_COPY[mode].placeholder}
        class="w-full text-base border border-gray-200 dark:border-gray-600 rounded-xl px-4 py-3 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 resize-y"
      ></textarea>
      {#if isShortDraft}
        <p class="text-xs text-amber-600 dark:text-amber-400">
          ⚠ A bare name or short phrase gives the model little to go on and can match unrelated questions that just sound similar. Paste the full question text for more reliable matches.
        </p>
      {/if}
      <button
        onclick={runSearch}
        disabled={!draft.trim() || status === 'loading-model' || status === 'loading-corpus' || status === 'searching'}
        class="px-4 py-2 text-sm font-medium rounded-lg transition-colors bg-primary-500 text-white hover:bg-primary-600 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed dark:disabled:bg-gray-700 dark:disabled:text-gray-500"
      >
        {#if status === 'loading-model'}
          Loading model (one-time, ~20MB)…
        {:else if status === 'loading-corpus'}
          Loading question index…
        {:else if status === 'searching'}
          Searching…
        {:else}
          {MODE_COPY[mode].cta}
        {/if}
      </button>
    </div>

    {#if status === 'error'}
      <p class="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
    {/if}

    {#if status === 'done'}
      {#if results.length === 0}
        <p class="text-sm text-gray-500 dark:text-gray-400">No matches found.</p>
      {:else}
        <div class="space-y-2">
          <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            {MODE_COPY[mode].resultsHeading}
          </p>
          {#each results as { question, score, matchedEntities } (question.id)}
            <ResultCard {question} {score} {matchedEntities} styleMode={mode} />
          {/each}
        </div>
      {/if}
    {/if}
  {/if}
</div>
