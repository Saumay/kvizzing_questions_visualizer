"""
LLM-based discussion role classification.

Sends each question's discussion to the LLM with full context (question text,
answer, asker) and asks it to classify each entry's role. This produces much
more accurate classifications than heuristics alone.

Roles:
  - attempt: someone trying to answer the question
  - hint: the asker giving a clue before the answer
  - confirmation: the asker confirming a correct answer
  - answer_reveal: the asker explaining/revealing the full answer
  - elaboration: anyone sharing educational info about the answer/topic
  - chat: banter, reactions, meta-quiz discussion, off-topic

Usage:
    python3 pipeline.py classify-discussion [--dry-run] [--date YYYY-MM-DD]
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

log = logging.getLogger("kvizzing")

_VALID_ROLES = {"attempt", "hint", "confirmation", "answer_reveal", "elaboration", "chat"}

_SYSTEM_PROMPT = "You classify quiz discussion messages. Return only valid JSON."

_USER_PROMPT_TEMPLATE = (
    "Classify each discussion message's role in these quiz Q&A threads.\n\n"
    "Roles:\n"
    "- attempt: someone trying to answer (before the answer is confirmed)\n"
    "- hint: the asker giving a clue before the answer is confirmed\n"
    "- confirmation: the asker confirming someone got the right answer\n"
    "- answer_reveal: the asker explaining the full answer or providing the answer\n"
    "- elaboration: anyone sharing educational info, context, or trivia about the answer/topic\n"
    "- chat: banter, reactions, jokes, meta-discussion about the quiz, off-topic\n\n"
    "{questions}\n\n"
    "Reply with JSON: {{\"question_id\": [[idx, \"role\"], ...], ...}}\n"
    "Keys are question numbers (as strings), values are arrays of [index, role] pairs.\n"
    "Only return the JSON object, nothing else."
)


def _build_question_block(qi: int, q: dict) -> str | None:
    """Build the prompt block for a single question. Returns None if no discussion."""
    disc = q.get("discussion", [])
    if not disc:
        return None
    q_text = (q.get("question_text") or "")[:300]
    answer = (q.get("answer_text") or "")[:150]
    asker = q.get("question_asker") or ""
    disc_lines = []
    for di, d in enumerate(disc):
        username = d.get("username", "?")
        text = (d.get("text") or "")[:200]
        is_asker = " [ASKER]" if username == asker else ""
        disc_lines.append(f"    [{di}] {username}{is_asker}: \"{text}\"")
    return (
        f"--- Question {qi} ---\n"
        f"Q: \"{q_text}\"\n"
        f"A: \"{answer}\"\n"
        f"Asker: {asker}\n"
        f"Discussion:\n" + "\n".join(disc_lines)
    )


def _call_llm(llm_client, prompt: str) -> dict:
    """Make a single LLM call and parse JSON response."""
    resp = llm_client.messages.create(
        model="",
        max_tokens=16384,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = (resp.content[0].text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    if not raw:
        return {}
    return json.loads(raw)


class _RateLimiter:
    """Simple token-bucket rate limiter for RPM."""
    def __init__(self, rpm: int):
        self._interval = 60.0 / rpm
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            if now < self._next_slot:
                time.sleep(self._next_slot - now)
            self._next_slot = max(now, self._next_slot) + self._interval


def classify_discussion(
    questions_by_date: dict[str, list[dict]],
    llm_client,
    dry_run: bool = False,
    batch_size: int = 100,  # max discussion entries per batch (not questions)
    max_workers: int = 3,
    rpm: int = 15,
) -> dict[str, int]:
    """
    Use LLM to classify discussion roles for all questions.

    Batches multiple questions per LLM call and processes batches
    concurrently (up to max_workers) with rate limiting.

    Args:
        questions_by_date: {date_str: [extraction_output entries]}
        llm_client: LLM client with .messages.create()
        dry_run: if True, log changes without modifying
        batch_size: questions per LLM call (default 15)
        max_workers: concurrent LLM requests (default 3)
        rpm: max requests per minute (default 15, matches Gemini free tier)

    Returns:
        {date_str: count_of_reclassified_entries}
    """
    # Collect all work items across all dates
    work_items: list[tuple[str, list[tuple[int, dict]], list[tuple[int, list[int]]], str]] = []

    for date_str in sorted(questions_by_date.keys()):
        qs = questions_by_date[date_str]
        if not qs:
            continue
        eligible = [(qi, q) for qi, q in enumerate(qs) if q.get("discussion")]
        if not eligible:
            continue

        # Batch by discussion entry count to avoid oversized LLM responses
        prompt_parts = []
        batch: list[tuple[int, dict]] = []
        batch_meta: list[tuple[int, list[int]]] = []
        batch_entry_count = 0

        def flush_batch():
            nonlocal prompt_parts, batch, batch_meta, batch_entry_count
            if prompt_parts:
                prompt = _USER_PROMPT_TEMPLATE.format(questions="\n\n".join(prompt_parts))
                work_items.append((date_str, list(batch), list(batch_meta), prompt))
            prompt_parts = []
            batch = []
            batch_meta = []
            batch_entry_count = 0

        for qi, q in eligible:
            disc_len = len(q.get("discussion", []))
            # If adding this question would exceed the limit, flush first
            if batch_entry_count > 0 and batch_entry_count + disc_len > batch_size:
                flush_batch()
            block = _build_question_block(qi, q)
            if not block:
                continue
            prompt_parts.append(block)
            batch.append((qi, q))
            batch_meta.append((qi, list(range(disc_len))))
            batch_entry_count += disc_len

        flush_batch()  # flush remaining

    if not work_items:
        return {}

    log.info("Processing %d batches (%d concurrent, %d RPM limit)…",
             len(work_items), max_workers, rpm)

    limiter = _RateLimiter(rpm)
    results: dict[str, int] = {}
    results_lock = threading.Lock()

    def process_batch(item):
        date_str, batch, batch_meta, prompt = item
        limiter.wait()
        try:
            llm_results = _call_llm(llm_client, prompt)
        except Exception as e:
            log.warning("  [%s] LLM classify failed for batch at Q#%d: %s",
                        date_str, batch[0][0], e)
            return (date_str, 0)

        qs = questions_by_date[date_str]
        changed = 0
        for qi, classifiable_indices in batch_meta:
            q = qs[qi]
            disc = q.get("discussion", [])
            qi_key = str(qi)
            if qi_key not in llm_results:
                continue
            for idx, role in llm_results[qi_key]:
                if idx >= len(disc) or role not in _VALID_ROLES:
                    continue
                old_role = disc[idx].get("role", "")
                if role != old_role:
                    if dry_run:
                        text = (disc[idx].get("text") or "")[:60]
                        user = disc[idx].get("username", "?")
                        log.info("  [%s] Q#%d [%d] %s → %s: %s: %s",
                                 date_str, qi, idx, old_role, role, user, text)
                    else:
                        disc[idx]["role"] = role
                    changed += 1
        return (date_str, changed)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(process_batch, item): item for item in work_items}
        for future in as_completed(futures):
            date_str, changed = future.result()
            if changed > 0:
                with results_lock:
                    results[date_str] = results.get(date_str, 0) + changed

    for date_str in sorted(results):
        if not dry_run:
            log.info("  [%s] Reclassified %d discussion entries", date_str, results[date_str])

    return results
