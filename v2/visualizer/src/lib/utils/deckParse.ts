// Parses an uploaded quiz-deck file (.pptx or .pdf) entirely in the browser
// into a flat list of slide/page entries, each with a best-guess question
// and answer split out via a simple heuristic (decks aren't standardized
// enough to parse reliably any other way): if a line within the slide looks
// like "A:"/"Answer:"/"Ans:", everything before it is the question and that
// line onward is the answer; otherwise, with exactly two text blocks, the
// first is the question and the second the answer; otherwise the whole
// slide is treated as the question with no answer.
import JSZip from 'jszip';

export type DeckImage = { url: string; filename: string };
export type DeckEntry = {
  index: number;
  question: string;
  answer: string;
  images: DeckImage[];
};

const ANSWER_PREFIX = /^(answer|ans|a)\s*[:.\-]\s*/i;

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
  if (blocks.length === 2) {
    return { question: blocks[0].trim(), answer: blocks[1].trim() };
  }
  return { question: blocks.join('\n').trim(), answer: '' };
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

async function parsePptx(file: File): Promise<DeckEntry[]> {
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

  const entries: DeckEntry[] = [];
  for (let i = 0; i < slidePaths.length; i++) {
    const { blocks, images } = await parsePptxSlide(zip, slidePaths[i]);
    if (blocks.length === 0 && images.length === 0) continue;
    const { question, answer } = splitQA(blocks);
    entries.push({ index: i + 1, question, answer, images });
  }
  return entries;
}

// --- PDF ------------------------------------------------------------------

async function parsePdf(file: File): Promise<DeckEntry[]> {
  // Dynamic import, same reasoning as the embedding model: keep the WASM/
  // worker bits out of the initial page bundle.
  const pdfjsLib = await import('pdfjs-dist');
  const workerSrc = (await import('pdfjs-dist/build/pdf.worker.mjs?url')).default;
  pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;

  const buf = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: buf }).promise;

  const entries: DeckEntry[] = [];
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
  if (name.endsWith('.pptx')) return parsePptx(file);
  if (name.endsWith('.pdf')) return parsePdf(file);
  throw new Error('Unsupported file type. Please upload a .pptx or .pdf file.');
}
