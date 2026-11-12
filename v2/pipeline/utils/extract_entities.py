"""
Extract named entities (people, places, organizations, events, works, etc.)
from every question + answer, so the Check Duplicates / Search-by-topic tool
can treat proper nouns as an exact-match-able signal instead of leaving them
to pure semantic similarity, which conflates look-alike names (e.g. "Shah
Jahan" vs "Shahrukh Khan" share no meaning but a similar name shape). Also
surfaced as its own filterable facet on the Feed, same pattern as tags/topics.

Model: spaCy en_core_web_sm, small, fast, fully local (no API cost, no
per-question LLM call over 18k+ questions, unlike the Gemini topic
enrichment stage). Only entity labels that denote actual proper nouns are
kept; numeric/date/quantity labels are dropped.

Install:
  pip3 install --user --break-system-packages spacy
  pip3 install --user --break-system-packages "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

Run from anywhere:
  python3 v2/pipeline/utils/extract_entities.py

Also called automatically from pipeline.py after every export (best-effort,
same pattern as generate_question_embeddings.py) so this never goes stale
without a visible signal: see pipeline.py's _maybe_regenerate_entities.

Output:
  v2/visualizer/static/data/entities.json          = [{tag, count, question_ids}], same shape as tags.json
  v2/visualizer/static/data/question_entities.json = {question_id: [entity, ...]}
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

V2_DIR = Path(__file__).parent.parent.parent
DEFAULT_OUTPUT_DIR = V2_DIR / "visualizer" / "static" / "data"

# Labels that denote actual proper nouns, excluding DATE, TIME, CARDINAL,
# ORDINAL, MONEY, PERCENT, QUANTITY, which spaCy also tags as "entities"
# but aren't proper nouns in the sense we want here.
ALLOWED_LABELS = {
    "PERSON", "ORG", "GPE", "LOC", "FAC", "EVENT",
    "WORK_OF_ART", "NORP", "PRODUCT", "LAW", "LANGUAGE",
}

_LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)

# Bare compass directions get mistagged as LOC/GPE by spaCy fairly often
# ("ruler of the East") but aren't proper nouns at all, so they never belong
# in the index no matter how they got extracted.
_STOPWORDS = {
    "east", "west", "north", "south",
    "eastern", "western", "northern", "southern",
    "northeast", "northwest", "southeast", "southwest",
}


def _normalize(text: str) -> str:
    t = text.strip()
    t = _LEADING_ARTICLE.sub("", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip(" .,'\"")


# Connect/riddle answers in this corpus are overwhelmingly written as
# "X = Name" or "X = Name, Y = Other Name" (e.g. "X = Shah Jahan, Y =
# Jahangir"). spaCy's statistical NER is trained on ordinary prose and
# routinely misses names in this bare label-equals-value shape, since it
# has no surrounding sentence to key off. A regex pass catches what spaCy drops.
_LABEL_EQUALS = re.compile(
    r"(?:^|[,;])\s*[A-Z]\s*=\s*([A-ZÀ-Ö][\w'&.\-]*(?:\s+[A-ZÀ-Ö][\w'&.\-]*){0,4})"
)


def _regex_entities(text: str) -> list[str]:
    found = []
    for m in _LABEL_EQUALS.finditer(text):
        # Cut off at a trailing parenthetical or comma-joined explanation,
        # e.g. "Shah Jahan (Peacock Throne...)" -> "Shah Jahan".
        candidate = re.split(r"[,(]", m.group(1))[0].strip()
        candidate = _normalize(candidate)
        if candidate and len(candidate) >= 3 and not candidate.isdigit():
            found.append(candidate)
    return found


def main(output_dir: Path | None = None) -> None:
    import spacy

    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    questions_json = output_dir / "questions.json"
    questions = json.loads(questions_json.read_text())

    nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])

    ids = [q["id"] for q in questions]
    raw_texts = [
        q["question"]["text"] + " " + (q["answer"]["text"] or "")
        for q in questions
    ]
    print(f"Extracting entities from {len(ids)} questions with spaCy ({nlp.meta['name']})...")

    question_entities: dict[str, list[str]] = {}
    entity_questions: dict[str, list[str]] = defaultdict(list)
    seen_casing: dict[str, str] = {}  # lowercase -> first-seen display casing

    docs = nlp.pipe(raw_texts, batch_size=64)
    for i, (qid, doc, raw_text) in enumerate(zip(ids, docs, raw_texts)):
        found: list[str] = []
        for ent in doc.ents:
            if ent.label_ not in ALLOWED_LABELS:
                continue
            norm = _normalize(ent.text)
            if len(norm) < 3 or norm.isdigit() or norm.lower() in _STOPWORDS:
                continue
            key = norm.lower()
            canonical = seen_casing.setdefault(key, norm)
            if canonical not in found:
                found.append(canonical)
        for norm in _regex_entities(raw_text):
            if norm.lower() in _STOPWORDS:
                continue
            key = norm.lower()
            canonical = seen_casing.setdefault(key, norm)
            if canonical not in found:
                found.append(canonical)
        if found:
            question_entities[qid] = found
            for e in found:
                entity_questions[e].append(qid)
        if (i + 1) % 2000 == 0:
            print(f"  {i + 1}/{len(ids)}...")

    entities_list = [
        {"tag": entity, "count": len(qids), "question_ids": qids}
        for entity, qids in sorted(entity_questions.items(), key=lambda kv: -len(kv[1]))
    ]

    (output_dir / "entities.json").write_text(json.dumps(entities_list, ensure_ascii=False) + "\n")
    (output_dir / "question_entities.json").write_text(json.dumps(question_entities, ensure_ascii=False) + "\n")

    print(f"Wrote entities.json ({len(entities_list)} unique entities)")
    print(f"Wrote question_entities.json ({len(question_entities)} questions with entities)")


if __name__ == "__main__":
    main()
