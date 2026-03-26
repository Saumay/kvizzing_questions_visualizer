"""
Stage 1 — Parse

Converts raw WhatsApp chat lines into structured message objects with UTC
timestamps. Filters system messages and deleted-message tombstones.

Input:  list of raw text lines from Stage 0
Output: list of message dicts:
  {
    "timestamp": "2026-03-16T07:18:47Z",   # UTC ISO 8601
    "username": "pratik.s.chandarana",
    "text": "Q7.",
    "has_media": true
  }
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from zoneinfo import ZoneInfo

# ── Regex patterns ─────────────────────────────────────────────────────────────

# Single flexible pattern that matches all known WhatsApp export formats:
#   [M/D/YY, HH:MM:SS] Username: text           (US 24-hour, actual format)
#   [M/D/YY, H:MM:SS AM/PM] Username: text      (US 12-hour, some exports)
#   [DD/MM/YYYY, HH:MM:SS] Username: text       (international)
# Capture groups: (date_str, time_str, username_raw, text)
_PATTERN_MSG = re.compile(
    r"^\u200e?\[(\d{1,2}/\d{1,2}/\d{2,4}),\s+([^\]]+)\]\s+([^:]+):\s*(.*)",
    re.DOTALL,
)

# Media placeholders inserted by WhatsApp in plain-text exports
_MEDIA_PATTERNS = re.compile(
    r"<(image|video|audio|document|sticker|gif) omitted>",
    re.IGNORECASE,
)

# System message substrings — lines matching these are dropped entirely.
# WhatsApp system messages appear as "[timestamp] GroupName: ..." or
# "[timestamp] text" with no username colon — we catch them by content.
_SYSTEM_SUBSTRINGS = (
    "end-to-end encrypted",
    "created this group",
    "added ",
    "removed ",
    "left",
    "changed the group",
    "changed their phone number",
    "changed this group",
    "joined using this group",
    "was added",
    "security code changed",
    "You joined from",
    "Messages and calls are",
    "missed voice call",
    "missed video call",
)

_DELETED_PATTERNS = re.compile(
    r"^(This message was deleted|You deleted this message)$",
    re.IGNORECASE,
)


def _is_system_line(username: str, text: str) -> bool:
    """Return True if this line is a WhatsApp system notification."""
    # System messages often have the group name as "username" and contain
    # characteristic substrings, OR have a username that contains special chars.
    text_lower = text.lower()
    for s in _SYSTEM_SUBSTRINGS:
        if s.lower() in text_lower:
            return True
    # Lines where the "username" is the group name (contains |, emoji clusters, etc.)
    # are system events — heuristic: group name lines often contain || or ‎
    if "||" in username or "\u200e" in username:
        return True
    return False


def _parse_timestamp(date_str: str, time_str: str, formats: list[str], tz: ZoneInfo) -> datetime:
    """Try each locale format until one parses successfully, then convert to UTC."""
    combined = f"{date_str}, {time_str.strip()}"
    for fmt in formats:
        try:
            local_dt = datetime.strptime(combined, fmt)
            aware_local = local_dt.replace(tzinfo=tz)
            return aware_local.astimezone(ZoneInfo("UTC"))
        except ValueError:
            continue
    raise ValueError(f"No locale format matched timestamp: {combined!r}")


def _apply_aliases(username: str, aliases: dict[str, str]) -> str:
    return aliases.get(username, username)


def run(
    lines: list[str],
    config: dict,
    aliases: Optional[dict[str, str]] = None,
) -> list[dict]:
    """
    Parse raw WhatsApp lines into structured message objects.

    Args:
        lines:   raw text lines from Stage 0
        config:  parsed pipeline_config.json
        aliases: optional username alias map from username_aliases.json

    Returns:
        List of message dicts with UTC timestamps.
    """
    source_tz = ZoneInfo(config["source_timezone"])
    locale_formats: list[str] = config["stage1"]["locale_formats"]
    aliases = aliases or {}

    messages: list[dict] = []
    current: Optional[dict] = None

    for line in lines:
        line_stripped = line.rstrip("\n").rstrip("\r")

        match = _PATTERN_MSG.match(line_stripped)

        if match:
            date_str, time_str, username_raw, text = match.groups()
            # Strip ~ and any Unicode whitespace (including U+202F narrow no-break space)
            username = username_raw.lstrip("~").strip()
            # Strip remaining leading Unicode whitespace characters
            username = username.lstrip("\u202f\u00a0 \t").strip()
            username = _apply_aliases(username, aliases)
            text = text.strip()

            # Drop system messages
            if _is_system_line(username, text):
                if current:
                    messages.append(current)
                current = None
                continue

            # Drop deleted message tombstones
            if _DELETED_PATTERNS.match(text):
                if current:
                    messages.append(current)
                current = None
                continue

            # Save previous message
            if current:
                messages.append(current)

            try:
                utc_dt = _parse_timestamp(date_str, time_str, locale_formats, source_tz)
            except ValueError:
                # Malformed timestamp — skip
                current = None
                continue

            has_media = bool(_MEDIA_PATTERNS.search(text))
            # Strip media placeholder from text
            clean_text = _MEDIA_PATTERNS.sub("", text).strip()

            current = {
                "timestamp": utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "username": username,
                "text": clean_text,
                "has_media": has_media,
            }
        else:
            # Continuation line (multi-line message) — append to current
            if current and line_stripped:
                # Skip lines that look like system events even as continuations
                if not any(s.lower() in line_stripped.lower() for s in _SYSTEM_SUBSTRINGS):
                    current["text"] = (current["text"] + "\n" + line_stripped).strip()

    if current:
        messages.append(current)

    return messages
