"""
LLM client — unified adapter exposing a .messages.create() interface
compatible with all pipeline stages.

Provider:
  GEMINI_API_KEY → GeminiClient (gemini-2.5-pro via OpenAI-compatible endpoint)
"""

from __future__ import annotations

import os


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


# ── Factory ────────────────────────────────────────────────────────────────────

def get_client():
    """Return a GeminiClient, or None if GEMINI_API_KEY is unset."""
    import logging
    log = logging.getLogger("kvizzing")

    try:
        client = GeminiClient()
        log.info("Using GeminiClient")
        return client
    except (ImportError, RuntimeError):
        log.warning("No LLM client available: set GEMINI_API_KEY.")
        return None
