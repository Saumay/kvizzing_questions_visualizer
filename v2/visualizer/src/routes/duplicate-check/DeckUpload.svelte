<script lang="ts">
  import type { DupMatch } from '$lib/utils/dupChecker';
  import { scorePct } from '$lib/utils/dupChecker';
  import { parseDeck, type DeckEntry } from '$lib/utils/deckParse';
  import ResultCard from './ResultCard.svelte';

  interface Props {
    checker: ReturnType<typeof import('$lib/utils/dupChecker').createDupChecker>;
  }
  const { checker }: Props = $props();

  type SlideState = DeckEntry & {
    id: string;
    include: boolean;
    matches: DupMatch[] | null;
  };

  let fileName = $state('');
  let slides = $state<SlideState[]>([]);
  let parseStatus = $state<'idle' | 'parsing' | 'done' | 'error'>('idle');
  let parseError = $state('');
  let checkStatus = $state<'idle' | 'loading-model' | 'checking' | 'done'>('idle');
  let checkProgress = $state(0); // 0..included.length
  let fileInput: HTMLInputElement | undefined = $state();
  let showExcluded = $state(false);

  async function handleFile(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    fileName = file.name;
    parseStatus = 'parsing';
    parseError = '';
    slides = [];
    checkStatus = 'idle';
    try {
      const entries = await parseDeck(file);
      slides = entries.map(entry => ({
        ...entry,
        id: `slide-${entry.index}`,
        include: entry.looksLikeQuestion,
        matches: null,
      }));
      parseStatus = 'done';
    } catch (err) {
      console.error(err);
      parseError = err instanceof Error ? err.message : 'Could not read that file.';
      parseStatus = 'error';
    }
  }

  function reset() {
    fileName = '';
    slides = [];
    parseStatus = 'idle';
    parseError = '';
    checkStatus = 'idle';
    checkProgress = 0;
    if (fileInput) fileInput.value = '';
  }

  async function checkAll() {
    const included = slides.filter(s => s.include && s.question.trim());
    if (included.length === 0) return;
    checkStatus = 'loading-model';
    checkProgress = 0;
    await checker.ensureModelLoaded();
    await checker.ensureCorpusLoaded();
    checkStatus = 'checking';
    for (const slide of included) {
      slide.matches = await checker.search(slide.question, 3);
      checkProgress++;
    }
    checkStatus = 'done';
  }

  const includedSlides = $derived(slides.filter(s => s.include));
  const excludedSlides = $derived(slides.filter(s => !s.include));
  const includedCount = $derived(includedSlides.length);
  const flaggedCount = $derived(
    slides.filter(s => s.matches && s.matches.length > 0 && scorePct(s.matches[0].score) >= 60).length
  );

  function topPct(slide: SlideState): number | null {
    if (!slide.matches || slide.matches.length === 0) return null;
    return scorePct(slide.matches[0].score);
  }

  function flagCls(pct: number | null): string {
    if (pct === null) return 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
    if (pct >= 80) return 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300';
    if (pct >= 60) return 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300';
    return 'bg-green-50 text-green-600 dark:bg-green-900/30 dark:text-green-300';
  }

  async function downloadPdf() {
    const { jsPDF } = await import('jspdf');
    const doc = new jsPDF({ unit: 'pt', format: 'a4' });
    const margin = 48;
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const contentWidth = pageWidth - margin * 2;
    let y = margin;

    function ensureSpace(h: number) {
      if (y + h > pageHeight - margin) {
        doc.addPage();
        y = margin;
      }
    }

    doc.setFontSize(18);
    doc.text('Duplicate Check Report', margin, y);
    y += 22;
    doc.setFontSize(10);
    doc.setTextColor(120);
    doc.text(`${fileName} - generated ${new Date().toLocaleString()}`, margin, y);
    doc.setTextColor(0);
    y += 28;

    const included = slides.filter(s => s.include);
    for (const slide of included) {
      ensureSpace(90);
      doc.setFontSize(12);
      doc.setFont('helvetica', 'bold');
      doc.text(`Slide ${slide.index}`, margin, y);
      y += 16;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(10);
      const qLines = doc.splitTextToSize(slide.question || '(no text extracted)', contentWidth);
      ensureSpace(qLines.length * 12);
      doc.text(qLines, margin, y);
      y += qLines.length * 12 + 4;

      if (slide.answer) {
        const aLines = doc.splitTextToSize(`Answer: ${slide.answer}`, contentWidth);
        ensureSpace(aLines.length * 12);
        doc.setTextColor(90);
        doc.text(aLines, margin, y);
        doc.setTextColor(0);
        y += aLines.length * 12 + 4;
      }

      if (slide.matches && slide.matches.length > 0) {
        const pct = scorePct(slide.matches[0].score);
        const label = pct >= 80 ? 'Very likely a duplicate' : pct >= 60 ? 'Similar theme' : 'Loosely related';
        doc.setFont('helvetica', 'bold');
        ensureSpace(14);
        doc.text(`${pct}% match - ${label}`, margin, y);
        y += 14;
        doc.setFont('helvetica', 'normal');
        const matchLines = doc.splitTextToSize(slide.matches[0].question.question.text, contentWidth);
        ensureSpace(matchLines.length * 12);
        doc.setTextColor(90);
        doc.text(matchLines, margin, y);
        doc.setTextColor(0);
        y += matchLines.length * 12;
      } else if (checkStatus === 'done') {
        ensureSpace(12);
        doc.setTextColor(0, 140, 0);
        doc.text('No close match found.', margin, y);
        doc.setTextColor(0);
        y += 12;
      }
      y += 16;
      ensureSpace(1);
      doc.setDrawColor(220);
      doc.line(margin, y - 8, pageWidth - margin, y - 8);
    }

    doc.save(`duplicate-check-${fileName.replace(/\.[^.]+$/, '')}.pdf`);
  }
</script>

<div class="space-y-4">
  {#if slides.length === 0}
    <div class="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl p-8 text-center">
      <input
        bind:this={fileInput}
        type="file"
        accept=".pptx,.pdf"
        onchange={handleFile}
        class="block w-full text-sm text-gray-600 dark:text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-primary-500 file:text-white hover:file:bg-primary-600 file:cursor-pointer"
      />
      <p class="text-xs text-gray-500 dark:text-gray-400 mt-3">
        Accepts .pptx or .pdf. Each slide/page is parsed into a question (and answer, if we can find one), checked against the full question bank.
      </p>
      {#if parseStatus === 'parsing'}
        <p class="text-sm text-primary-600 dark:text-primary-400 mt-3">Parsing {fileName}…</p>
      {/if}
      {#if parseStatus === 'error'}
        <p class="text-sm text-red-600 dark:text-red-400 mt-3">{parseError}</p>
      {/if}
    </div>
  {:else}
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div>
        <p class="text-sm font-medium text-gray-800 dark:text-gray-200">{fileName}</p>
        <p class="text-xs text-gray-500 dark:text-gray-400">
          {slides.length} slide{slides.length === 1 ? '' : 's'} found, {includedCount} included
          {#if checkStatus === 'done'}
            &middot; <span class={flaggedCount > 0 ? 'text-amber-600 dark:text-amber-400 font-medium' : ''}>{flaggedCount} flagged as likely duplicates</span>
          {/if}
        </p>
      </div>
      <div class="flex items-center gap-2">
        {#if checkStatus === 'done'}
          <button
            onclick={downloadPdf}
            class="px-3 py-1.5 text-sm font-medium rounded-lg border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Download PDF report
          </button>
        {/if}
        <button
          onclick={checkAll}
          disabled={includedCount === 0 || checkStatus === 'loading-model' || checkStatus === 'checking'}
          class="px-3 py-1.5 text-sm font-medium rounded-lg bg-primary-500 text-white hover:bg-primary-600 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed dark:disabled:bg-gray-700 dark:disabled:text-gray-500"
        >
          {#if checkStatus === 'loading-model'}
            Loading model…
          {:else if checkStatus === 'checking'}
            Checking {checkProgress}/{includedCount}…
          {:else if checkStatus === 'done'}
            Re-check all
          {:else}
            Check all for duplicates
          {/if}
        </button>
        <button onclick={reset} class="px-3 py-1.5 text-sm text-gray-500 dark:text-gray-400 hover:underline">
          Upload a different file
        </button>
      </div>
    </div>

    {#snippet slideCard(slide: SlideState)}
      {@const pct = topPct(slide)}
      <div class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 p-4">
        <div class="flex items-start gap-3">
          <label class="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 flex-shrink-0 pt-1 cursor-pointer">
            <input type="checkbox" bind:checked={slide.include} />
            Slide {slide.index}
          </label>
          <div class="flex-1 min-w-0 space-y-2">
            <textarea
              bind:value={slide.question}
              rows="5"
              placeholder="Question text (edit if the extraction looks off)"
              class="w-full text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-2.5 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 resize-y"
            ></textarea>
            <textarea
              bind:value={slide.answer}
              rows="2"
              placeholder="Answer (optional)"
              class="w-full text-xs border border-gray-200 dark:border-gray-600 rounded-lg px-2.5 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 resize-y"
            ></textarea>
            {#if slide.images.length > 0}
              <div class="flex gap-2 flex-wrap">
                {#each slide.images as img (img.url)}
                  <img src={img.url} alt="Slide {slide.index} image" class="h-16 w-16 object-cover rounded-lg border border-gray-200 dark:border-gray-600" />
                {/each}
              </div>
            {/if}
          </div>
          {#if pct !== null}
            <span class="flex-shrink-0 text-xs font-semibold px-2 py-1 rounded-full {flagCls(pct)}">
              {pct}%
            </span>
          {/if}
        </div>
        {#if slide.matches && slide.matches.length > 0}
          <div class="mt-3 pl-7 space-y-2">
            {#each slide.matches.slice(0, 3) as m (m.question.id)}
              <ResultCard question={m.question} score={m.score} matchedEntities={m.matchedEntities} />
            {/each}
          </div>
        {:else if slide.matches && slide.matches.length === 0}
          <p class="mt-3 pl-7 text-xs text-green-600 dark:text-green-400">No close match found.</p>
        {/if}
      </div>
    {/snippet}

    <div class="space-y-3">
      {#each includedSlides as slide (slide.id)}
        {@render slideCard(slide)}
      {/each}
    </div>

    {#if excludedSlides.length > 0}
      <div>
        <button
          type="button"
          onclick={() => showExcluded = !showExcluded}
          class="text-xs text-gray-500 dark:text-gray-400 hover:underline"
        >
          {showExcluded ? 'Hide' : 'Show'} {excludedSlides.length} excluded slide{excludedSlides.length === 1 ? '' : 's'} (titles, dividers, safety notices — tick one back on if we got it wrong)
        </button>
        {#if showExcluded}
          <div class="space-y-3 mt-3">
            {#each excludedSlides as slide (slide.id)}
              {@render slideCard(slide)}
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</div>
