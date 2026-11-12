// Parses an uploaded quiz-deck file (.pptx or .pdf) entirely in the browser
// into a flat list of slide/page entries. Decks aren't standardized, so
// question/answer splitting goes through two heuristic layers:
//
// 1. Same-slide: if a line within the slide looks like "A:"/"Answer:"/
//    "Ans:", everything before it is the question and that line onward is
//    the answer; otherwise, with exactly two text blocks (and neither looks
//    like a bare "QUESTION"/"ANSWER" header), the first is the question and
//    the second the answer; otherwise the whole slide is the question.
// 2. Cross-slide (finalizeEntries, below): many decks instead put the
//    question and its answer on two separate slides, each starting with a
//    bare "QUESTION"/"ANSWER" header line (optionally numbered, e.g.
//    "QUESTION 1" / "ANSWER 1"), often with unrelated slides (round
//    dividers, safety notices, credits) in between. When that convention is
//    detected anywhere in the deck, the matching answer slide is merged
//    into its question's entry instead of appearing as its own row, and any
//    slide that isn't itself a recognized question header defaults to
//    excluded (looksLikeQuestion: false) rather than relying on word count.
//    A few headers (e.g. "Tie-breaker") label both the question and its
//    answer with the identical word rather than distinct Q/A words; the
//    first occurrence of such a header is treated as the question and the
//    next matching occurrence as its answer.
import JSZip from 'jszip';

export type DeckImage = { url: string; filename: string };
export type DeckEntry = {
  index: number;
  question: string;
  answer: string;
  images: DeckImage[];
  looksLikeQuestion: boolean;
};
type RawDeckEntry = Omit<DeckEntry, 'looksLikeQuestion'>;

const ANSWER_PREFIX = /^(answer|ans|a)\s*[:.\-]\s*/i;
// A line that is JUST a header like "QUESTION", "QUESTION 1" or "Q #1" -
// anchored at both ends so an actual question sentence that happens to
// start with the word "Question" (e.g. "Question: name the river...") still
// has trailing text and so doesn't match.
const QUESTION_HEADER = /^q(?:uestion)?\s*#?\s*([\w.-]*)\s*:?\s*$/i;
const ANSWER_HEADER = /^a(?:nswer|ns)?\s*#?\s*([\w.-]*)\s*:?\s*$/i;
// Some headers (e.g. "Tie-breaker") label both halves of a pair with the
// SAME word instead of distinct "QUESTION"/"ANSWER" words, so role (question
// vs. answer) can't be read off the word itself - it's just whichever one of
// a matching pair shows up first vs. second.
const PAIRED_HEADER = /^tie[\s-]?breakers?\s*#?\s*([\w.-]*)\s*:?\s*$/i;
// Fallback when no cross-slide header convention is detected anywhere in
// the deck: a slide with more than this many words is probably real
// question content rather than a title/credits/divider slide.
const TITLE_WORD_COUNT_FLOOR = 4;

function headerMatch(text: string, re: RegExp): { label: string; rest: string } | null {
  const lines = text.split('\n');
  const m = lines[0].trim().match(re);
  if (!m) return null;
  return { label: (m[1] ?? '').trim().toLowerCase(), rest: lines.slice(1).join('\n').trim() };
}

function splitQA(blocks: string[]): { question: string; answer: string } {
  for (let i = 0; i < blocks.length; i++) {
    const lines = blocks[i].split('\n');
    for (let j = 0; j < lines.length; j++) {
      if (ANSWER_PREFIX.test(lines[j].trim())) {
        const before = [...blocks.slice(0, i), lines.slice(0, j).join('\n')].filter(Boolean).join('\n').trim();
        const answerLine = lines[j].trim().replace(ANSWER_PREFIX, '');
        const after = [answerLine, ...lines.slice(j + 1), ...blocks.slice(i + 1)].filter(Boolean).join('\n').trim();
        return { question: before, answer: after };
      }
    }
  }
  // A lone header line ("QUESTION 1") paired with a second block isn't a
  // question/answer pair, it's a header plus its own content - don't treat
  // the second block as an "answer" in that case.
  if (blocks.length === 2 && !QUESTION_HEADER.test(blocks[0]) && !ANSWER_HEADER.test(blocks[0])) {
    return { question: blocks[0].trim(), answer: blocks[1].trim() };
  }
  return { question: blocks.join('\n').trim(), answer: '' };
}

// Cross-slide pairing + the default include/exclude guess, applied once
// over the whole deck regardless of source format.
function finalizeEntries(raw: RawDeckEntry[]): DeckEntry[] {
  const usesHeaderConvention = raw.some(e => headerMatch(e.question, QUESTION_HEADER) !== null);
  const result: DeckEntry[] = [];
  const pendingByLabel = new Map<string, DeckEntry>();
  let lastUnanswered: DeckEntry | null = null;

  const pairedPending = new Map<string, DeckEntry>();

  for (const r of raw) {
    const pm = headerMatch(r.question, PAIRED_HEADER);
    if (pm) {
      const key = `paired:${pm.label}`;
      const pending = pairedPending.get(key);
      if (pending && !pending.answer) {
        pending.answer = pm.rest || r.question;
        if (r.images.length) pending.images = [...pending.images, ...r.images];
        pairedPending.delete(key);
        if (pending === lastUnanswered) lastUnanswered = null;
        continue; // second occurrence: merged in as the answer to the first
      }
      const entry: DeckEntry = { ...r, question: pm.rest || r.question, looksLikeQuestion: true };
      result.push(entry);
      pairedPending.set(key, entry);
      lastUnanswered = entry.answer ? null : entry;
      continue;
    }

    const qm = headerMatch(r.question, QUESTION_HEADER);
    if (qm) {
      const entry: DeckEntry = { ...r, question: qm.rest || r.question, looksLikeQuestion: true };
      result.push(entry);
      if (qm.label) pendingByLabel.set(qm.label, entry);
      lastUnanswered = entry.answer ? null : entry;
      continue;
    }

    const am = headerMatch(r.question, ANSWER_HEADER);
    if (am) {
      const target = (am.label && pendingByLabel.get(am.label)) || lastUnanswered;
      if (target && !target.answer) {
        target.answer = am.rest || r.question;
        if (r.images.length) target.images = [...target.images, ...r.images];
        if (am.label) pendingByLabel.delete(am.label);
        if (target === lastUnanswered) lastUnanswered = null;
        continue; // merged into its question's entry, not its own row
      }
      // Labeled/unlabeled answer with nothing pending to attach to: fall
      // through and keep it as its own (excluded-by-default) entry so nothing
      // silently vanishes.
    }

    const looksLikeQuestion = usesHeaderConvention
      ? false // a non-header slide in a header-convention deck: divider, credits, safety notice, or an orphan answer
      : r.question.trim().split(/\s+/).filter(Boolean).length > TITLE_WORD_COUNT_FLOOR;
    result.push({ ...r, looksLikeQuestion });
  }
  return result;
}

// --- PPTX ---------------------------------------------------------------

function parseXml(xmlText: string): Document {
  return new DOMParser().parseFromString(xmlText, 'application/xml');
}

const PPTX_NS = {
  r: 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
};

async function parsePptxSlide(
  zip: JSZip,
  slidePath: string
): Promise<{ blocks: string[]; images: DeckImage[] }> {
  const xmlText = await zip.file(slidePath)!.async('text');
  const doc = parseXml(xmlText);

  // Each <p:sp> (shape) with a text body becomes one block, paragraphs
  // joined by newlines, in document order (the best available proxy for
  // reading order without real layout analysis).
  const blocks: string[] = [];
  const shapes = doc.getElementsByTagName('p:sp');
  for (let i = 0; i < shapes.length; i++) {
    const paras = shapes[i].getElementsByTagName('a:p');
    const paraTexts: string[] = [];
    for (let p = 0; p < paras.length; p++) {
      const runs = paras[p].getElementsByTagName('a:t');
      let line = '';
      for (let r = 0; r < runs.length; r++) line += runs[r].textContent ?? '';
      paraTexts.push(line);
    }
    const block = paraTexts.join('\n').trim();
    if (block) blocks.push(block);
  }

  // Resolve embedded images via the slide's rels file: a:blip r:embed -> rId
  // -> relationship target -> media file in the zip.
  const images: DeckImage[] = [];
  const slideName = slidePath.split('/').pop()!;
  const relsPath = `ppt/slides/_rels/${slideName}.rels`;
  const relsFile = zip.file(relsPath);
  if (relsFile) {
    const relsXml = parseXml(await relsFile.async('text'));
    const relById = new Map<string, string>();
    const rels = relsXml.getElementsByTagName('Relationship');
    for (let i = 0; i < rels.length; i++) {
      const rel = rels[i];
      if ((rel.getAttribute('Type') ?? '').endsWith('/image')) {
        relById.set(rel.getAttribute('Id')!, rel.getAttribute('Target')!);
      }
    }
    const blips = doc.getElementsByTagName('a:blip');
    for (let i = 0; i < blips.length; i++) {
      const rId = blips[i].getAttributeNS(PPTX_NS.r, 'embed') ?? blips[i].getAttribute('r:embed') ?? '';
      if (!rId) continue;
      const target = relById.get(rId);
      if (!target) continue;
      // Targets are relative to ppt/slides/, e.g. "../media/image1.png".
      const mediaPath = new URL(target, 'zip:///ppt/slides/').pathname.replace(/^\//, '');
      const mediaFile = zip.file(mediaPath);
      if (!mediaFile) continue;
      const blob = await mediaFile.async('blob');
      images.push({ url: URL.createObjectURL(blob), filename: mediaPath.split('/').pop()! });
    }
  }

  return { blocks, images };
}

async function parsePptx(file: File): Promise<RawDeckEntry[]> {
  const zip = await JSZip.loadAsync(await file.arrayBuffer());

  // Slide order comes from the presentation's own slide-id list, not file
  // naming, since slides can be reordered without renumbering their files.
  const presXml = parseXml(await zip.file('ppt/presentation.xml')!.async('text'));
  const presRelsXml = parseXml(await zip.file('ppt/_rels/presentation.xml.rels')!.async('text'));
  const relTargetById = new Map<string, string>();
  const presRels = presRelsXml.getElementsByTagName('Relationship');
  for (let i = 0; i < presRels.length; i++) {
    relTargetById.set(presRels[i].getAttribute('Id')!, presRels[i].getAttribute('Target')!);
  }
  const sldIds = presXml.getElementsByTagName('p:sldId');
  const slidePaths: string[] = [];
  for (let i = 0; i < sldIds.length; i++) {
    const rId = sldIds[i].getAttributeNS(PPTX_NS.r, 'id');
    const target = rId ? relTargetById.get(rId) : null;
    if (target) slidePaths.push(`ppt/${target.replace(/^\.?\/?/, '')}`);
  }

  const entries: RawDeckEntry[] = [];
  for (let i = 0; i < slidePaths.length; i++) {
    const { blocks, images } = await parsePptxSlide(zip, slidePaths[i]);
    if (blocks.length === 0 && images.length === 0) continue;
    const { question, answer } = splitQA(blocks);
    entries.push({ index: i + 1, question, answer, images });
  }
  return entries;
}

// --- PDF ------------------------------------------------------------------

async function parsePdf(file: File): Promise<RawDeckEntry[]> {
  // Dynamic import, same reasoning as the embedding model: keep the WASM/
  // worker bits out of the initial page bundle.
  const pdfjsLib = await import('pdfjs-dist');
  const workerSrc = (await import('pdfjs-dist/build/pdf.worker.mjs?url')).default;
  pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;

  const buf = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: buf }).promise;

  const entries: RawDeckEntry[] = [];
  for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
    const page = await pdf.getPage(pageNum);
    const content = await page.getTextContent();

    // Group text items into lines by y-position (items on the same visual
    // line share a transform[5] within a small tolerance), then into blocks
    // by vertical gap, approximating the paragraph/shape grouping pptx
    // parsing gets for free from the XML structure.
    type Item = { str: string; x: number; y: number };
    const items: Item[] = (content.items as any[])
      .filter(it => typeof it.str === 'string')
      .map(it => ({ str: it.str, x: it.transform[4], y: it.transform[5] }));

    const lineTolerance = 2;
    const lines: { y: number; text: string }[] = [];
    for (const it of items.sort((a, b) => b.y - a.y || a.x - b.x)) {
      const line = lines.find(l => Math.abs(l.y - it.y) <= lineTolerance);
      if (line) line.text += it.str;
      else lines.push({ y: it.y, text: it.str });
    }
    lines.sort((a, b) => b.y - a.y);

    const blocks: string[] = [];
    let current: string[] = [];
    let lastY: number | null = null;
    const paragraphGap = 18;
    for (const line of lines) {
      const text = line.text.trim();
      if (!text) continue;
      if (lastY !== null && lastY - line.y > paragraphGap && current.length) {
        blocks.push(current.join('\n'));
        current = [];
      }
      current.push(text);
      lastY = line.y;
    }
    if (current.length) blocks.push(current.join('\n'));

    if (blocks.length === 0) continue;
    const { question, answer } = splitQA(blocks);
    // Image extraction isn't supported for PDF decks yet (pdf.js requires
    // walking each page's operator list and re-encoding image XObjects,
    // notably heavier than the pptx case where images are just zip entries).
    entries.push({ index: pageNum, question, answer, images: [] });
  }
  return entries;
}

export async function parseDeck(file: File): Promise<DeckEntry[]> {
  const name = file.name.toLowerCase();
  let raw: RawDeckEntry[];
  if (name.endsWith('.pptx')) raw = await parsePptx(file);
  else if (name.endsWith('.pdf')) raw = await parsePdf(file);
  else throw new Error('Unsupported file type. Please upload a .pptx or .pdf file.');
  return finalizeEntries(raw);
}
