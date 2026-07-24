"""
Detect Stable Horde's "CENSORED" placeholder card: a plain black image with
centered white text ("CENSORED / NSFW content detected...") returned instead
of real artwork when a worker's own content filter trips (false positives are
common on the free/anonymous queue). These aren't NSFW content themselves —
they're broken, unusable output that needs regenerating.

The placeholder is near-solid black outside the text, which no legitimate
generated illustration comes close to (validated against the full existing
session-image set: the placeholder scores ~0.76 "black fraction", the next
darkest real image is ~0.08 — see the wide margin below).
"""

from __future__ import annotations

from pathlib import Path

BLACK_PIXEL_THRESHOLD = 25   # 0-255; a channel below this counts as "black"
BLACK_FRACTION_THRESHOLD = 0.3  # fraction of sampled pixels that must be black


def is_censored_placeholder(image: bytes | Path) -> bool:
    from PIL import Image

    img = Image.open(image) if isinstance(image, Path) else Image.open(__import__("io").BytesIO(image))
    img = img.convert("RGB").resize((96, 32))
    pixels = list(img.getdata())

    black = sum(
        1 for r, g, b in pixels
        if r < BLACK_PIXEL_THRESHOLD and g < BLACK_PIXEL_THRESHOLD and b < BLACK_PIXEL_THRESHOLD
    )
    return (black / len(pixels)) >= BLACK_FRACTION_THRESHOLD
