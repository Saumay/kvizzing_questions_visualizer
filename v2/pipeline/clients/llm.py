"""
LLM client — unified adapter exposing a .messages.create() interface
compatible with all pipeline stages.

Providers (selected via env var LLM_PROVIDER):
  - "gemini"      (default; needs GEMINI_API_KEY) → GeminiClient
  - "claude_file" → ClaudeFileClient (file-queue handoff to a Claude session
                    that watches the queue dir, reads request files, and
                    writes response files; lets pipeline.py backfill run
                    end-to-end with Claude as the LLM)

ClaudeFileClient queue layout:
  v2/data/llm_queue/<uuid>.request.json   ← written by client, read by Claude
  v2/data/llm_queue/<uuid>.response.json  ← written by Claude, read by client
  v2/data/llm_queue/<uuid>.done           ← marker after client consumes response
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path


# ── Response shims ─────────────────────────────────────────────────────────────

class _Content:
    __slots__ = ("text",)
    def __init__(self, text: str):
        self.text = text

class _Response:
    __slots__ = ("content",)
    def __init__(self, text: str):
        self.content = [_Content(text)]

class _Messages:
    def __init__(self, create_fn):
        self._create_fn = create_fn

    def create(self, *, model: str, max_tokens: int, system: str, messages: list, **_):
        return self._create_fn(model=model, max_tokens=max_tokens, system=system, messages=messages)


# ── Gemini client ──────────────────────────────────────────────────────────────

_GEMINI_MODEL = "gemini-2.5-pro"
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiClient:
    """
    Gemini via its OpenAI-compatible endpoint.
    Requires the `openai` package and GEMINI_API_KEY env var.
    Free tier: 15 RPM, 1M token context window.
    """

    def __init__(self):
        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package required for GeminiClient: pip install openai")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY environment variable.")
        self._client = openai.OpenAI(base_url=_GEMINI_BASE_URL, api_key=api_key)
        self.messages = _Messages(self._create)

    def _create(self, *, model: str, max_tokens: int, system: str, messages: list) -> _Response:
        response = self._client.chat.completions.create(
            model=_GEMINI_MODEL,
            max_tokens=max_tokens,
            temperature=0.0,
            messages=[{"role": "system", "content": system}] + messages,
        )
        return _Response(response.choices[0].message.content)


# ── Claude file-queue client ───────────────────────────────────────────────────

# Queue dir lives under v2/data/llm_queue. clients/llm.py is at v2/pipeline/clients/llm.py
# so the queue dir is two levels up + data/llm_queue.
_QUEUE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "llm_queue"
# Default poll interval and timeout. Override via env if needed.
_POLL_SECONDS = float(os.environ.get("CLAUDE_POLL_SECONDS", "1.0"))
_TIMEOUT_SECONDS = float(os.environ.get("CLAUDE_TIMEOUT_SECONDS", "7200"))  # 2 hr default


class ClaudeFileClient:
    """
    File-queue handoff to an external Claude session.

    On every .messages.create():
      1. Write <uuid>.request.json with {model, max_tokens, system, messages, ...}
      2. Poll for <uuid>.response.json until it appears (or timeout).
      3. Read response, return as _Response.
      4. Touch <uuid>.done so the responder can clean up.

    The Claude session watches _QUEUE_DIR via Read/Write tools, generates
    extraction or enrichment per the system prompt, and writes the response.
    """

    def __init__(self, queue_dir: Path | None = None,
                 poll_seconds: float = _POLL_SECONDS,
                 timeout_seconds: float = _TIMEOUT_SECONDS):
        self.queue_dir = Path(queue_dir or _QUEUE_DIR)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.messages = _Messages(self._create)

    def _create(self, *, model: str, max_tokens: int, system: str, messages: list) -> _Response:
        request_id = uuid.uuid4().hex[:12]
        req_path = self.queue_dir / f"{request_id}.request.json"
        resp_path = self.queue_dir / f"{request_id}.response.json"
        done_path = self.queue_dir / f"{request_id}.done"

        request = {
            "id": request_id,
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        # Write atomically: tmp then rename so the responder never sees a partial file.
        tmp_path = req_path.with_suffix(".request.json.tmp")
        tmp_path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(req_path)

        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            if resp_path.exists():
                # Tolerate the responder writing-in-progress: retry parse on partial reads.
                for _ in range(3):
                    try:
                        body = json.loads(resp_path.read_text(encoding="utf-8"))
                        break
                    except json.JSONDecodeError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError(f"ClaudeFileClient: response {request_id} unparseable")
                content = body.get("content")
                if content is None:
                    raise RuntimeError(f"ClaudeFileClient: response {request_id} missing 'content' field")
                done_path.touch()
                return _Response(content)
            time.sleep(self.poll_seconds)

        raise TimeoutError(
            f"ClaudeFileClient: no response for {request_id} after {self.timeout_seconds:.0f}s "
            f"(check {self.queue_dir})"
        )


# ── Factory ────────────────────────────────────────────────────────────────────

def get_client():
    """Return an LLM client based on LLM_PROVIDER env var (default: gemini).

    Values:
      - "gemini" / unset → GeminiClient (needs GEMINI_API_KEY)
      - "claude_file" → ClaudeFileClient (file-queue handoff)
    """
    import logging
    log = logging.getLogger("kvizzing")

    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()

    if provider == "claude_file":
        client = ClaudeFileClient()
        log.info("Using ClaudeFileClient (queue: %s)", client.queue_dir)
        return client

    try:
        client = GeminiClient()
        log.info("Using GeminiClient")
        return client
    except (ImportError, RuntimeError):
        log.warning("No LLM client available: set GEMINI_API_KEY or LLM_PROVIDER=claude_file.")
        return None
