"""
Stage 4 — Enrich

Assigns primary + secondary topic and tags to each KVizzingQuestion via LLM.

Questions that already have 2+ topics are skipped (idempotent).
Questions with 0 or 1 topic are (re-)enriched so both categories are populated.
Questions are sent to the LLM in batches for efficiency.

Input:  list of KVizzingQuestion objects from Stage 3
Output: list of KVizzingQuestion objects with topics + tags populated
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
import sys
import time
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "schema"))
from schema import KVizzingQuestion, TopicCategory

log = logging.getLogger("kvizzing")


def _parse_json(text: str) -> list:
    """Parse JSON from LLM output, stripping markdown fences if present."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


# ── Tag normalisation ─────────────────────────────────────────────────────────
# Tags that describe question FORMAT, not subject matter — never store these.
_FORMAT_TAGS = {
    "identify", "anagram", "wordplay", "connect", "clickbait",
    "real life", "naming", "weird", "multi-part", "factual",
    "battle", "pun", "fill in the blank",
}

# Tags to rename on ingest
_RENAME_TAGS: dict[str, str] = {
    "badly explained plots": "badly explained",
    "pun": "puns",
}


def _normalize_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for tag in tags:
        tag = _RENAME_TAGS.get(tag, tag)
        if tag in _FORMAT_TAGS:
            continue
        if tag not in seen:
            result.append(tag)
            seen.add(tag)
    return result


_TOPIC_LIST_STR = ", ".join(t.value for t in TopicCategory)

_ENRICH_SYSTEM_PROMPT = """\
You are classifying quiz questions from a WhatsApp trivia group.

For each question you receive, assign:
1. primary_topic — the single best-fitting topic from the list below
2. secondary_topic — a second topic if the question genuinely spans two domains. null if not applicable.
3. tertiary_topic — a third topic if genuinely warranted. null in most cases.
4. tags — 2–5 lowercase subject/category tags for fine-grained categorisation

VALID TOPICS: """ + _TOPIC_LIST_STR + """

TOPIC GUIDELINES — choose the MOST SPECIFIC category that fits:
- mathematics: equations, geometry, number theory, statistics, puzzles involving math
- science: physics, chemistry, biology, astronomy, experiments (NOT math — use mathematics)
- medicine: health, diseases, anatomy, drugs, medical history
- cinema: movies, TV shows, actors, directors, film industry, Bollywood, Hollywood
- music: songs, albums, musicians, bands, instruments, music theory, concerts
- entertainment: gaming, anime, comics, board games, general pop culture (NOT cinema or music)
- military: wars, battles, weapons, armed forces, defense strategy
- politics: elections, governments, political figures, policies, geopolitics
- religion: religious texts, practices, festivals, theology, religious history
- linguistics: language origins, grammar, scripts, translation (NOT etymology — use etymology for word origins)
- nature: wildlife, ecology, animals, plants, environment, conservation
- mythology: myths, legends, epics, mythological figures
- history: historical events, figures, empires, civilizations (NOT military — use military for war-specific)
- geography: countries, cities, maps, landmarks, travel, physical geography
- literature: books, authors, poetry, literary movements, publishing
- art_culture: painting, sculpture, dance, theater, cultural practices, architecture
- food_drink: cuisine, recipes, restaurants, beverages, food history
- business: companies, brands, entrepreneurs, economics, finance, markets
- etymology: word origins, phrase origins, naming conventions
- technology: software, hardware, internet, inventions, engineering
- sports: games, athletes, tournaments, records, sporting history
- meme: meme culture, internet humor, viral content
- general: ONLY as a last resort when no specific category fits

CRITICAL: Prefer specific categories over general ones. A question about a battle should be \
"military" not "history". A question about a Bollywood film should be "cinema" not "entertainment". \
A question about a math puzzle should be "mathematics" not "science".

USING CONTEXT:
- session_theme / session_announcement: tells you the quiz's overall theme — use this to \
inform topic assignment (e.g. a session themed "Bollywood" → questions are likely cinema).
- hints: clues from the asker — often reveal the domain (e.g. "think about chemistry" → science).
- elaborations: post-answer context — reveals what the question was really about.
- Use ALL available context to pick the most accurate, specific topic.

TAG RULES:
- Tags must describe SUBJECT MATTER, never question format (no "identify", "anagram", "connect", etc.)
- Exception: "badly explained" is accepted for that quiz format.
- Be specific: "bollywood" not just "india", "ww2" not just "war".
- Use consistent forms, avoid near-duplicates.
- Include the session_theme as a tag if relevant (e.g. "bollywood", "ipl", "sanskrit poetry").

You will receive a JSON array. Return a JSON array of the same length, same order:
{"id": "<id>", "primary_topic": "<topic>", "secondary_topic": "<topic> or null", "tertiary_topic": "<topic> or null", "tags": ["tag1", "tag2"]}

Return ONLY valid JSON. No markdown fences, no explanation.
"""


def _build_batch_prompt(questions: list[KVizzingQuestion], fresh: bool = False) -> str:
    items = []
    for q in questions:
        item: dict = {
            "id": q.id,
            "question": q.question.text,
            "answer": q.answer.text,
        }

        # Include session context if available
        if q.session:
            if q.session.theme:
                item["session_theme"] = q.session.theme
            if q.session.announcement:
                item["session_announcement"] = q.session.announcement

        # Include hints from discussion
        hints = [e.text for e in (q.discussion or []) if e.role.value == "hint" and e.text]
        if hints:
            item["hints"] = hints

        # Include answer elaborations
        elaborations = [e.text for e in (q.discussion or [])
                        if e.role.value == "elaboration" and e.text]
        if elaborations:
            item["elaborations"] = elaborations

        # If not doing fresh recategorization, include existing topics for context
        if q.question.topics and not fresh:
            item["current_topics"] = [t.value for t in q.question.topics]

        items.append(item)
    return json.dumps(items, ensure_ascii=False)


def _call_llm(
    questions: list[KVizzingQuestion],
    config: dict,
    llm_client,
    fresh: bool = False,
) -> list[dict]:
    """
    Call the LLM with a batch of questions and return enrichment dicts.
    Retries on rate limit with exponential backoff.
    Returns empty list on unrecoverable failure.
    """
    model: str = config["stage4"]["llm_model"]
    max_retries: int = config["stage4"]["llm_max_retries"]
    base_delay: float = config["stage4"]["llm_retry_base_delay_seconds"]

    user_prompt = _build_batch_prompt(questions, fresh=fresh)

    for attempt in range(max_retries):
        try:
            response = llm_client.messages.create(
                model=model,
                max_tokens=4096,
                system=_ENRICH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw_text = response.content[0].text
            return _parse_json(raw_text)
        except json.JSONDecodeError as e:
            log.warning(
                "Stage4 LLM returned invalid JSON (attempt %d/%d): %s\nRaw response (first 500 chars): %s",
                attempt + 1, max_retries, e, raw_text[:500] if 'raw_text' in dir() else "<no response>",
            )
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                log.warning("Stage4 retrying in %.1fs…", delay)
                time.sleep(delay)
                continue
            return []
        except Exception as e:
            err_lower = str(e).lower()
            is_transient = any(kw in err_lower for kw in [
                "429", "503", "rate_limit", "resource_exhausted", "unavailable",
                "timeout", "timed out", "connection error", "connection reset",
                "remoteprotocol", "remotedisconnected",
            ])
            if is_transient and attempt < max_retries - 1:
                delay = max(base_delay * (2 ** attempt), 30)
                log.warning("Stage4 transient error — retrying in %.1fs (attempt %d/%d)…", delay, attempt + 1, max_retries)
                time.sleep(delay)
                continue
            log.error("Stage4 LLM call failed: %s", e, exc_info=True)
            if is_transient:
                return []  # Don't crash pipeline on transient errors
            raise
    return []


def _apply_enrichment(
    question: KVizzingQuestion,
    enrichment: dict,
) -> KVizzingQuestion:
    """Return a copy of question with primary + optional secondary topic and tags applied."""
    primary_str = enrichment.get("primary_topic", "") or enrichment.get("topic", "")
    secondary_str = enrichment.get("secondary_topic") or ""
    tertiary_str = enrichment.get("tertiary_topic") or ""
    tags = _normalize_tags(enrichment.get("tags", []))

    try:
        primary = TopicCategory(primary_str)
    except ValueError:
        primary = TopicCategory.general

    topics: list[TopicCategory] = [primary]
    for extra_str in (secondary_str, tertiary_str):
        if extra_str:
            try:
                extra = TopicCategory(extra_str)
                if extra not in topics:
                    topics.append(extra)
            except ValueError:
                pass

    # Pydantic v2: model_copy(update=...) for nested field replacement
    updated_question = question.question.model_copy(
        update={"topics": topics, "tags": tags}
    )
    return question.model_copy(update={"question": updated_question})


def enrich(
    questions: list[KVizzingQuestion],
    config: dict,
    llm_client,
    fresh: bool = False,
) -> list[KVizzingQuestion]:
    """
    Enrich a list of questions with up to 3 topics and tags via LLM.
    If fresh=True, recategorize ALL questions from scratch (ignore existing topics).
    Otherwise, questions with 3 topics already are skipped.
    """
    batch_size: int = config["stage4"]["llm_batch_size"]

    if fresh:
        to_enrich = list(questions)
        already_done: dict[str, KVizzingQuestion] = {}
    else:
        to_enrich = [q for q in questions if len(q.question.topics) < 2]
        already_done = {q.id: q for q in questions if len(q.question.topics) >= 2}

    # Build an id→result map for the enriched ones
    enriched_map: dict[str, KVizzingQuestion] = dict(already_done)

    # Process in batches
    for batch_start in range(0, len(to_enrich), batch_size):
        batch = to_enrich[batch_start : batch_start + batch_size]
        try:
            results = _call_llm(batch, config, llm_client, fresh=fresh)
        except Exception:
            log.warning("Stage4: enrichment batch failed — storing questions without topics.")
            for q in batch:
                enriched_map[q.id] = q
            continue

        # Index results by id
        results_by_id = {r["id"]: r for r in results if isinstance(r, dict) and "id" in r}

        for q in batch:
            if q.id in results_by_id:
                enriched_map[q.id] = _apply_enrichment(q, results_by_id[q.id])
            else:
                # LLM didn't return this question — keep as-is
                enriched_map[q.id] = q

    # Return in original order
    return [enriched_map[q.id] for q in questions]


def run(
    questions: list[KVizzingQuestion],
    config: dict,
    llm_client=None,
) -> list[KVizzingQuestion]:
    """
    Stage 4 entry point. If llm_client is None (test mode), returns questions unchanged.
    """
    if llm_client is None:
        return questions

    return enrich(questions, config, llm_client)
