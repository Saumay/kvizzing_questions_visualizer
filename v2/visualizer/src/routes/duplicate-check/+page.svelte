<script lang="ts">
  import { getContext, onMount } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import type { Question } from '$lib/types';
  import { formatDateTz } from '$lib/utils/time';

  const store = getContext<QuestionStore>('store');
  const tzCtx = getContext<{ value: string }>('timezone');
  const questions = store.getQuestions();
  const questionById = new Map(questions.map(q => [q.id, q]));

  const MODEL_ID = 'Xenova/all-MiniLM-L6-v2';

  type Mode = 'duplicate' | 'topic';
  let mode = $state<Mode>('duplicate');

  const MODE_COPY: Record<Mode, { title: string; description: string; placeholder: string; cta: string; resultsHeading: string }> = {
    duplicate: {
      title: 'Check for Duplicates',
      description: "Paste your draft question and search the full question bank for similar ones already asked, catching reworded repeats, not just exact-text matches. Everything runs in your browser, so your question is never sent anywhere or seen by anyone else.",
      placeholder: 'e.g. "This Mughal emperor commissioned a mausoleum in Agra for his wife Mumtaz Mahal, completed around 1653 in white marble inlaid with precious stones. Name the emperor and the monument."',
      cta: 'Check for duplicates',
      resultsHeading: 'Closest matches',
    },
    topic: {
      title: 'Search by Topic',
      description: "Describe what you're looking for in plain language — a person, event, theme, anything — and find existing questions about it, even if they're worded completely differently. Same engine as duplicate-check, just read as \"what's been asked about X\" instead of \"has this exact question been asked\".",
      placeholder: 'e.g. "questions about Shah Jahan" or "anything about 90s Bollywood music"…',
      cta: 'Search',
      resultsHeading: 'Related questions',
    },
  };

  // Corpus embeddings + the model pipeline are loaded once (lazily, on first
  // check) and cached at module scope so repeat searches on this page don't
  // re-fetch or re-init anything.
  let corpusIds: string[] | null = null;
  let corpusVectors: Float32Array | null = null; // dequantized, row-major [count x dim]
  let corpusDim = 0;
  let extractor: ((text: string, opts: { pooling: string; normalize: boolean }) => Promise<{ data: Float32Array }>) | null = null;

  // All known proper nouns extracted from the corpus (see
  // utils/extract_entities.py), longest-first so "Shah Jahan" is checked
  // before a shorter entity that might also happen to be a substring of it.
  const entityVocabulary = store.getEntities().map(e => e.tag).sort((a, b) => b.length - a.length);

  function escapeRegex(s: string): string {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  // Finds which known entities are literally present in the query text.
  // This is the fix for "Shah Jahan" matching a Shahrukh Khan question: an
  // exact, word-boundary match against the real entity vocabulary extracted
  // from the corpus is a much stronger signal than embedding similarity
  // alone, which can conflate proper nouns that merely look alike.
  function findMatchedEntities(text: string): string[] {
    const matched: string[] = [];
    for (const entity of entityVocabulary) {
      const re = new RegExp(`\\b${escapeRegex(entity)}\\b`, 'i');
      if (re.test(text)) matched.push(entity);
    }
    // Drop a match that's wholly contained in a longer match already found
    // (e.g. don't also report "Shah" once "Shah Jahan" already matched).
    return matched.filter((e, idx) =>
      !matched.slice(0, idx).some(longer => longer !== e && longer.toLowerCase().includes(e.toLowerCase()))
    );
  }

  // Splits text into segments so matched entity spans can be rendered with
  // a highlight — built as data (not {@html}) since the question/answer
  // text is plain, not markup.
  function highlightSegments(text: string, entities: string[]): { text: string; hl: boolean }[] {
    if (entities.length === 0) return [{ text, hl: false }];
    const pattern = new RegExp(`\\b(${[...entities].sort((a, b) => b.length - a.length).map(escapeRegex).join('|')})\\b`, 'gi');
    const segments: { text: string; hl: boolean }[] = [];
    let lastIndex = 0;
    for (const m of text.matchAll(pattern)) {
      if (m.index! > lastIndex) segments.push({ text: text.slice(lastIndex, m.index), hl: false });
      segments.push({ text: m[0], hl: true });
      lastIndex = m.index! + m[0].length;
    }
    if (lastIndex < text.length) segments.push({ text: text.slice(lastIndex), hl: false });
    return segments;
  }

  let draft = $state('');
  // A lone name or a couple of words gives the embedding model nothing to
  // disambiguate with (e.g. "Shah Jahan" alone can match a Bollywood-cast
  // question just because it shares a similar name shape) — full sentences
  // work far better, so nudge toward that instead of silently returning
  // weak matches.
  const draftWordCount = $derived(draft.trim() ? draft.trim().split(/\s+/).length : 0);
  const isShortDraft = $derived(draftWordCount > 0 && draftWordCount < 6);
  let status = $state<'idle' | 'loading-model' | 'loading-corpus' | 'searching' | 'done' | 'error'>('idle');
  let errorMessage = $state('');
  let results = $state<{ question: Question; score: number; matchedEntities: string[] }[]>([]);

  type IndexStatus = { ok: boolean; corpus_count: number | null; total_questions: number | null; last_success: string | null };
  let indexStatus = $state<IndexStatus | null>(null);

  onMount(async () => {
    try {
      const r = await fetch('/data/question_embeddings_status.json');
      if (r.ok) indexStatus = await r.json();
    } catch {
      // Best-effort — the page still works without this, it just won't show a freshness line.
    }
  });

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

  async function runSearch() {
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

      // Take a wider candidate pool than the final 10 so an exact entity
      // match that embedding similarity alone ranked outside the top 10
      // still gets a chance to surface once boosted below.
      const matchedQueryEntities = findMatchedEntities(text);
      const pool = scored.slice(0, 100)
        .map(({ i, score }) => ({ question: questionById.get(corpusIds![i])!, score }))
        .filter(r => r.question)
        .map(r => ({
          ...r,
          matchedEntities: matchedQueryEntities.filter(e => store.getQuestionEntities(r.question.id).includes(e)),
        }));

      pool.sort((a, b) => {
        if (a.matchedEntities.length !== b.matchedEntities.length) return b.matchedEntities.length - a.matchedEntities.length;
        return b.score - a.score;
      });

      results = pool.slice(0, 10);
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
    if (mode === 'topic') {
      if (pct >= 80) return 'Highly relevant';
      if (pct >= 60) return 'Relevant';
      return 'Loosely related';
    }
    if (pct >= 80) return 'Very likely a duplicate';
    if (pct >= 60) return 'Similar theme';
    return 'Loosely related';
  }

  function scoreCls(pct: number): string {
    if (mode === 'topic') {
      if (pct >= 80) return 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-300';
      if (pct >= 60) return 'bg-sky-50 text-sky-600 dark:bg-sky-900/30 dark:text-sky-300';
      return 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
    }
    if (pct >= 80) return 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300';
    if (pct >= 60) return 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300';
    return 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
  }

  function switchMode(next: Mode) {
    if (mode === next) return;
    mode = next;
    results = [];
    status = 'idle';
    errorMessage = '';
  }

  // Where a question actually came from isn't obvious from its text alone —
  // surface it explicitly rather than making the reader infer it.
  function sourceBadge(question: Question): { label: string; cls: string } {
    if (!question.session) {
      return { label: 'General question', cls: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300' };
    }
    const session = store.getSessionById(question.session.id);
    if (session?.is_live) {
      return { label: '⭐ Live quiz', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' };
    }
    return { label: 'Quiz session', cls: 'bg-sky-50 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300' };
  }
</script>

<div class="space-y-6 max-w-2xl">
  <div>
    <div class="flex items-center gap-3 flex-wrap">
      <h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">{MODE_COPY[mode].title}</h1>
      <div class="inline-flex items-center rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm overflow-hidden">
        <button
          onclick={() => switchMode('duplicate')}
          class="px-3 py-1.5 transition-colors {mode === 'duplicate' ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'}"
        >Check duplicates</button>
        <button
          onclick={() => switchMode('topic')}
          class="px-3 py-1.5 transition-colors border-l border-gray-200 dark:border-gray-600 {mode === 'topic' ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'}"
        >Search by topic</button>
      </div>
    </div>
    <p class="text-sm text-gray-500 dark:text-gray-400 mt-2">
      {MODE_COPY[mode].description}
    </p>
    {#if indexStatus}
      <p class="text-xs mt-2 flex items-center gap-1.5 {indexStatus.ok && indexStatus.corpus_count === indexStatus.total_questions ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'}">
        {#if indexStatus.ok && indexStatus.corpus_count === indexStatus.total_questions}
          ✓ Index up to date — covers all {indexStatus.total_questions?.toLocaleString()} questions
        {:else if indexStatus.corpus_count !== null && indexStatus.total_questions !== null}
          ⚠ Index covers {indexStatus.corpus_count.toLocaleString()} of {indexStatus.total_questions.toLocaleString()} questions — may be stale
        {:else}
          ⚠ Index status unavailable
        {/if}
      </p>
    {/if}
  </div>

  <div class="space-y-3">
    <textarea
      bind:value={draft}
      rows="4"
      placeholder={MODE_COPY[mode].placeholder}
      class="w-full text-sm border border-gray-200 dark:border-gray-600 rounded-xl px-4 py-3 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 resize-y"
    ></textarea>
    {#if isShortDraft}
      <p class="text-xs text-amber-600 dark:text-amber-400">
        ⚠ A bare name or short phrase gives the model little to go on and can match unrelated questions that just sound similar — paste the full question text for more reliable matches.
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
          {@const pct = scorePct(score)}
          {@const source = sourceBadge(question)}
          {@const questionSegments = highlightSegments(question.question.text, matchedEntities)}
          {@const answerSegments = question.answer?.text ? highlightSegments(question.answer.text, matchedEntities) : null}
          <a
            href="/question/{question.id}"
            class="block bg-ui-card rounded-xl border {matchedEntities.length > 0 ? 'border-green-300 dark:border-green-700' : 'border-gray-200 dark:border-gray-700'} shadow-sm hover:shadow-md hover:border-primary-200 transition-all p-4"
          >
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
                    <span class="inline-block text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                      ✓ Exact match: {matchedEntities.join(', ')}
                    </span>
                  {/if}
                </div>
                <p class="text-sm text-gray-800 dark:text-gray-200 line-clamp-3">
                  {#each questionSegments as seg}{#if seg.hl}<mark class="bg-green-200 dark:bg-green-700/60 text-inherit rounded px-0.5">{seg.text}</mark>{:else}{seg.text}{/if}{/each}
                </p>
                {#if answerSegments}
                  <p class="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-1">
                    <span class="font-medium">Answer:</span> {#each answerSegments as seg}{#if seg.hl}<mark class="bg-green-200 dark:bg-green-700/60 text-inherit rounded px-0.5">{seg.text}</mark>{:else}{seg.text}{/if}{/each}
                  </p>
                {/if}
              </div>
              <span class="flex-shrink-0 text-xs font-semibold px-2 py-1 rounded-full {scoreCls(pct)}" title={scoreLabel(pct)}>
                {pct}%
              </span>
            </div>
            <p class="text-xs text-gray-500 dark:text-gray-400 mt-2">
              {question.question.asker} &middot; {formatDateTz(question.date, tzCtx?.value ?? 'Europe/London')}
              {#if question.session?.theme}&middot; {question.session.theme}{/if}
            </p>
          </a>
        {/each}
      </div>
    {/if}
  {/if}
</div>
