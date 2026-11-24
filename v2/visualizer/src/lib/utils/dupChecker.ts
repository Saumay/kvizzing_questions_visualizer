import type { QuestionStore } from '$lib/stores/questionStore';
import type { Question } from '$lib/types';

const MODEL_ID = 'Xenova/all-MiniLM-L6-v2';

export type DupMatch = { question: Question; score: number; matchedEntities: string[] };

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function entityMatchRanges(text: string, entities: string[]): [number, number][] {
  if (entities.length === 0) return [];
  const pattern = new RegExp(`\\b(${[...entities].sort((a, b) => b.length - a.length).map(escapeRegex).join('|')})\\b`, 'gi');
  const ranges: [number, number][] = [];
  for (const m of text.matchAll(pattern)) ranges.push([m.index!, m.index! + m[0].length]);
  return ranges;
}

function tokenizeWords(text: string): { word: string; start: number; end: number }[] {
  const tokens: { word: string; start: number; end: number }[] = [];
  const re = /\S+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) tokens.push({ word: m[0], start: m.index, end: m.index + m[0].length });
  return tokens;
}

function normWord(w: string): string {
  return w.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
}

// Finds contiguous runs (>= minRun words) in `candidateWords` that also
// appear, in the same order, somewhere in `queryWords` - a word-level LCS
// rather than a naive per-word set overlap, so "the" or "and" scattered
// through unrelated sentences can't each count as a "match" on their own.
function sharedRunIndices(candidateWords: string[], queryWords: string[], minRun: number): Set<number> {
  const n = candidateWords.length, m = queryWords.length;
  if (n === 0 || m === 0) return new Set();
  const dp: Uint16Array[] = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = candidateWords[i] && candidateWords[i] === queryWords[j]
        ? dp[i + 1][j + 1] + 1
        : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const matchedIdx: number[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (candidateWords[i] && candidateWords[i] === queryWords[j]) {
      matchedIdx.push(i);
      i++; j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      i++;
    } else {
      j++;
    }
  }
  const result = new Set<number>();
  let runStart = 0;
  for (let k = 0; k <= matchedIdx.length; k++) {
    const contiguous = k > runStart && k < matchedIdx.length && matchedIdx[k] === matchedIdx[k - 1] + 1;
    if (!contiguous) {
      if (k - runStart >= minRun) for (let r = runStart; r < k; r++) result.add(matchedIdx[r]);
      runStart = k;
    }
  }
  return result;
}

function wordOverlapRanges(text: string, queryText: string, minRun = 3): [number, number][] {
  const candTokens = tokenizeWords(text);
  const queryWords = tokenizeWords(queryText).map(t => normWord(t.word)).filter(Boolean);
  const candWords = candTokens.map(t => normWord(t.word));
  const matched = sharedRunIndices(candWords, queryWords, minRun);
  return [...matched].map(idx => [candTokens[idx].start, candTokens[idx].end] as [number, number]);
}

function mergeRanges(ranges: [number, number][]): [number, number][] {
  if (ranges.length === 0) return [];
  const sorted = [...ranges].sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [sorted[0]];
  for (const [start, end] of sorted.slice(1)) {
    const last = merged[merged.length - 1];
    if (start <= last[1]) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }
  return merged;
}

// Splits text into segments so matched spans can be rendered with a
// highlight. Built as data (not {@html}) since the question/answer text is
// plain, not markup. Highlights two independent kinds of evidence: entities
// from the known vocabulary (always), and - when `queryText` is given - any
// contiguous phrase (>= minRun words) shared with the user's own draft, so a
// near word-for-word duplicate reads as mostly green, not just its proper
// nouns.
export function highlightSegments(
  text: string,
  entities: string[],
  queryText?: string,
  minRun = 3
): { text: string; hl: boolean }[] {
  const ranges = mergeRanges([
    ...entityMatchRanges(text, entities),
    ...(queryText ? wordOverlapRanges(text, queryText, minRun) : []),
  ]);
  if (ranges.length === 0) return [{ text, hl: false }];
  const segments: { text: string; hl: boolean }[] = [];
  let lastIndex = 0;
  for (const [start, end] of ranges) {
    if (start > lastIndex) segments.push({ text: text.slice(lastIndex, start), hl: false });
    segments.push({ text: text.slice(start, end), hl: true });
    lastIndex = end;
  }
  if (lastIndex < text.length) segments.push({ text: text.slice(lastIndex), hl: false });
  return segments;
}

export function scorePct(score: number): number {
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}

// Encapsulates the corpus/model loading and scoring logic shared between the
// single-query duplicate-check flow and the bulk deck-upload flow, so both
// run the exact same entity + embedding blend rather than two copies that
// could drift apart.
export function createDupChecker(store: QuestionStore) {
  const questions = store.getQuestions();
  const questionById = new Map(questions.map(q => [q.id, q]));
  const totalQuestions = questions.length;

  // All known proper nouns extracted from the corpus (see
  // utils/extract_entities.py), longest-first so "Shah Jahan" is checked
  // before a shorter entity that might also happen to be a substring of it.
  const entityVocabulary = store.getEntities().map(e => e.tag).sort((a, b) => b.length - a.length);
  const entitiesByTag = new Map(store.getEntities().map(e => [e.tag, e]));

  let corpusIds: string[] | null = null;
  let corpusVectors: Float32Array | null = null; // dequantized, row-major [count x dim]
  let corpusDim = 0;
  let extractor: ((text: string, opts: { pooling: string; normalize: boolean }) => Promise<{ data: Float32Array }>) | null = null;

  // Finds which known entities are literally present in the query text. An
  // exact, word-boundary match against the real entity vocabulary extracted
  // from the corpus is a much stronger signal than embedding similarity
  // alone, which can conflate proper nouns that merely look alike (e.g.
  // "Shah Jahan" vs a Shahrukh Khan question).
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

  // How rare an entity is across the whole corpus: common words (India,
  // count in the thousands) are weak evidence of true relevance even when
  // literally present, while a name mentioned in only a handful of
  // questions is strong evidence. log(total / count), normalized to [0, 1]
  // by the maximum possible value (count = 1).
  function entityRarity(entity: string): number {
    const entry = entitiesByTag.get(entity);
    if (!entry || entry.count <= 0) return 0;
    return Math.log(totalQuestions / entry.count) / Math.log(totalQuestions);
  }

  // A short or bare query gives the embedding model nothing to disambiguate
  // with, so entity overlap should matter a lot there. A long, already
  // descriptive query embeds well on its own, so a coincidental one-word
  // overlap shouldn't be allowed to perturb an already well-functioning
  // ranking. Full weight at 3 words or fewer, zero weight at 15 words or
  // more, linear between.
  const ENTITY_WEIGHT_FLOOR_WORDS = 3;
  const ENTITY_WEIGHT_CEILING_WORDS = 15;
  function entityWeightForQuery(wordCount: number): number {
    if (wordCount <= ENTITY_WEIGHT_FLOOR_WORDS) return 1;
    if (wordCount >= ENTITY_WEIGHT_CEILING_WORDS) return 0;
    return 1 - (wordCount - ENTITY_WEIGHT_FLOOR_WORDS) / (ENTITY_WEIGHT_CEILING_WORDS - ENTITY_WEIGHT_FLOOR_WORDS);
  }

  // Combines embedding similarity with entity overlap into one continuous
  // score, rather than a binary "boosted or not" bucket. Capped at 1.2 total
  // rarity contribution so a result that happens to share several
  // merely-uncommon entities can't run away with the score; the embedding
  // similarity is still the base signal.
  const ENTITY_BONUS_SCALE = 0.6;
  const ENTITY_BONUS_CAP = 1.2;
  function blendedScore(embeddingScore: number, matchedEntities: string[], queryWordCount: number): number {
    if (matchedEntities.length === 0) return embeddingScore;
    const rarity = Math.min(matchedEntities.reduce((sum, e) => sum + entityRarity(e), 0), ENTITY_BONUS_CAP);
    return embeddingScore + entityWeightForQuery(queryWordCount) * ENTITY_BONUS_SCALE * rarity;
  }

  async function ensureCorpusLoaded() {
    if (corpusVectors) return;
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
    // Dynamic import: this pulls in WASM/ONNX runtime bits that only make
    // sense in the browser, so keep it out of the initial page bundle and
    // well away from anything SvelteKit might touch during prerendering.
    const { pipeline } = await import('@huggingface/transformers');
    // q8 (quantized) variant: ~23MB vs ~86MB for full fp32 weights, matching
    // the corpus embeddings which are also int8-quantized on the Python side.
    extractor = (await pipeline('feature-extraction', MODEL_ID, { dtype: 'q8' })) as typeof extractor extends infer T ? NonNullable<T> : never;
  }

  async function search(text: string, topN = 10): Promise<DupMatch[]> {
    await ensureModelLoaded();
    await ensureCorpusLoaded();

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

    // Capture every question's score before sorting, needed below to score
    // an exact-entity-match candidate that embedding similarity alone
    // didn't rank highly enough to land in the top slice.
    const scoreByQid = new Map<string, number>();
    for (const { i, score } of scored) scoreByQid.set(corpusIds![i], score);

    scored.sort((a, b) => b.score - a.score);

    // A bare or short query can embed too generically for the real matches
    // to land in the top candidates by similarity alone. Directly pull in
    // every question that shares an exact entity match with the query,
    // regardless of its embedding rank, and let those compete on equal
    // footing with the top similarity-ranked candidates.
    const matchedQueryEntities = findMatchedEntities(text);
    const entityQuestionIds = new Set<string>();
    for (const entity of matchedQueryEntities) {
      const entry = entitiesByTag.get(entity);
      if (entry) for (const qid of entry.question_ids) entityQuestionIds.add(qid);
    }

    const topIds = scored.slice(0, 100).map(({ i }) => corpusIds![i]);
    const candidateIds = new Set([...topIds, ...entityQuestionIds]);
    const queryWordCount = text.split(/\s+/).filter(Boolean).length;

    const pool = [...candidateIds]
      .map(qid => {
        const question = questionById.get(qid);
        if (!question) return null;
        const embeddingScore = scoreByQid.get(qid) ?? 0;
        const matchedEntities = matchedQueryEntities.filter(e => store.getQuestionEntities(qid).includes(e));
        const score = blendedScore(embeddingScore, matchedEntities, queryWordCount);
        return { question, score, matchedEntities };
      })
      .filter((r): r is DupMatch => r !== null);

    pool.sort((a, b) => b.score - a.score);
    return pool.slice(0, topN);
  }

  return { ensureModelLoaded, ensureCorpusLoaded, search, findMatchedEntities };
}
