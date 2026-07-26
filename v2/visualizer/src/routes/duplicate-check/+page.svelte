<script lang="ts">
  import { getContext } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import type { Question } from '$lib/types';
  import { formatDateTz } from '$lib/utils/time';

  const store = getContext<QuestionStore>('store');
  const tzCtx = getContext<{ value: string }>('timezone');
  const questions = store.getQuestions();
  const questionById = new Map(questions.map(q => [q.id, q]));

  const MODEL_ID = 'Xenova/all-MiniLM-L6-v2';

  // Corpus embeddings + the model pipeline are loaded once (lazily, on first
  // check) and cached at module scope so repeat searches on this page don't
  // re-fetch or re-init anything.
  let corpusIds: string[] | null = null;
  let corpusVectors: Float32Array | null = null; // dequantized, row-major [count x dim]
  let corpusDim = 0;
  let extractor: ((text: string, opts: { pooling: string; normalize: boolean }) => Promise<{ data: Float32Array }>) | null = null;

  let draft = $state('');
  let status = $state<'idle' | 'loading-model' | 'loading-corpus' | 'searching' | 'done' | 'error'>('idle');
  let errorMessage = $state('');
  let results = $state<{ question: Question; score: number }[]>([]);

  async function ensureCorpusLoaded() {
    if (corpusVectors) return;
    status = 'loading-corpus';
    const [bin, meta] = await Promise.all([
      fetch('/data/question_embeddings.bin').then(r => r.arrayBuffer()),
      fetch('/data/question_embeddings_meta.json').then(r => r.json()),
    ]);
    const quantized = new Int8Array(bin);
    const scale = meta.scale as number;
    const dequantized = new Float32Array(quantized.length);
    for (let i = 0; i < quantized.length; i++) dequantized[i] = quantized[i] / scale;
    corpusVectors = dequantized;
    corpusIds = meta.ids as string[];
    corpusDim = meta.dim as number;
  }

  async function ensureModelLoaded() {
    if (extractor) return;
    status = 'loading-model';
    // Dynamic import — this pulls in WASM/ONNX runtime bits that only make
    // sense in the browser, so keep it out of the initial page bundle and
    // well away from anything SvelteKit might touch during prerendering.
    const { pipeline } = await import('@huggingface/transformers');
    // q8 (quantized) variant: ~23MB vs ~86MB for full fp32 weights, matching
    // the corpus embeddings which are also int8-quantized on the Python side.
    extractor = (await pipeline('feature-extraction', MODEL_ID, { dtype: 'q8' })) as typeof extractor extends infer T ? NonNullable<T> : never;
  }

  async function checkForDuplicates() {
    const text = draft.trim();
    if (!text) return;
    errorMessage = '';
    results = [];
    try {
      await ensureModelLoaded();
      await ensureCorpusLoaded();
      status = 'searching';

      const output = await extractor!(text, { pooling: 'mean', normalize: true });
      const query = output.data; // unit-normalized, length === corpusDim

      const count = corpusIds!.length;
      const scored: { i: number; score: number }[] = [];
      for (let i = 0; i < count; i++) {
        const base = i * corpusDim;
        let dot = 0;
        for (let d = 0; d < corpusDim; d++) dot += corpusVectors![base + d] * query[d];
        scored.push({ i, score: dot });
      }
      scored.sort((a, b) => b.score - a.score);

      results = scored.slice(0, 10)
        .map(({ i, score }) => ({ question: questionById.get(corpusIds![i])!, score }))
        .filter(r => r.question);
      status = 'done';
    } catch (e) {
      console.error(e);
      errorMessage = e instanceof Error ? e.message : 'Something went wrong.';
      status = 'error';
    }
  }

  function scorePct(score: number): number {
    return Math.round(Math.max(0, Math.min(1, score)) * 100);
  }

  function scoreLabel(pct: number): string {
    if (pct >= 80) return 'Very likely a duplicate';
    if (pct >= 60) return 'Similar theme';
    return 'Loosely related';
  }

  function scoreCls(pct: number): string {
    if (pct >= 80) return 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300';
    if (pct >= 60) return 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300';
    return 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
  }
</script>

<div class="space-y-6 max-w-2xl">
  <div>
    <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Check for Duplicates</h1>
    <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
      Paste your draft question and search the full question bank for similar ones already asked — catches
      reworded repeats, not just exact-text matches. Runs entirely in your browser; nothing is sent anywhere.
    </p>
  </div>

  <div class="space-y-3">
    <textarea
      bind:value={draft}
      rows="4"
      placeholder="Type or paste the question you're drafting…"
      class="w-full text-sm border border-gray-200 dark:border-gray-600 rounded-xl px-4 py-3 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 resize-y"
    ></textarea>
    <button
      onclick={checkForDuplicates}
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
        Check for duplicates
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
          Closest matches
        </p>
        {#each results as { question, score } (question.id)}
          {@const pct = scorePct(score)}
          <a
            href="/question/{question.id}"
            class="block bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md hover:border-primary-200 transition-all p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <p class="text-sm text-gray-800 dark:text-gray-200 flex-1 min-w-0 line-clamp-2">
                {question.question.text}
              </p>
              <span class="flex-shrink-0 text-xs font-semibold px-2 py-1 rounded-full {scoreCls(pct)}" title={scoreLabel(pct)}>
                {pct}%
              </span>
            </div>
            <p class="text-xs text-gray-500 dark:text-gray-400 mt-2">
              {question.question.asker} &middot; {formatDateTz(question.date, tzCtx?.value ?? 'Europe/London')}
            </p>
          </a>
        {/each}
      </div>
    {/if}
  {/if}
</div>
