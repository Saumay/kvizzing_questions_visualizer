"""generate-deck-banners: curated, title-specific banner art for Live Sessions.

Per-round session images (generate_session_images.py) are generic/thematic
per round; the Decks/"Live Sessions" page only needs ONE representative
banner per series or standalone deck, and tying that to "the latest round's
photo" goes stale every time a new round lands. This generates a dedicated,
hand-curated-prompt banner per series/standalone id instead, saved to
v2/visualizer/static/images/decks/{id}.jpg, read by
decks/+page.svelte's seriesImageUrl()/standaloneImageUrl().

Usage:
    python3 -m utils.generate_deck_banners            # generate missing banners
    python3 -m utils.generate_deck_banners --force ID  # regenerate one banner
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

try:
    from generate_session_images import generate, is_censored_placeholder  # run directly from utils/
except ImportError:
    from utils.generate_session_images import generate, is_censored_placeholder  # run via pipeline.py / -m utils.

V2_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = V2_DIR / "visualizer" / "static" / "images" / "decks"

# Hand-written per-title prompts — no text/words, no faces (same constraints
# as generate_session_images.py's NEGATIVE_PROMPT), wide banner, painterly.
BANNER_PROMPTS: dict[str, str] = {
    # --- series ---
    "gauntlet": "two stylized boxing gloves clashing under a dramatic spotlight in a dark arena, bold red and gold tones, competitive energy, dynamic illustration, wide banner",
    "kviz-o-krazzy": "colorful carnival-style tournament bracket illustration, quarterfinals semifinals and final, vibrant circus tent colors, playful energetic composition, wide banner",
    "mtv-tournament": "retro music-television tournament bracket, neon pop-art colors, trophy and music notes, vibrant 90s aesthetic, wide banner",
    "megakviz": "an enormous glowing brain bursting with colorful knowledge icons — books, planets, atoms, musical notes — epic mega-scale illustration, rich jewel tones, wide banner",
    "movie-quiz-bijal": "world cinema film reels unspooling across a stylized globe, iconic cinema silhouettes, warm golden cinematic lighting, painterly illustration, wide banner",
    "buzzing-whatsapp-namrata": "stylized smartphone chat bubbles buzzing with energy, green and white messaging-app palette, playful abstract illustration, wide banner",
    "buzzing-entertainment": "vibrant collage of entertainment icons — film clapperboard, music notes, theater masks, popcorn — colorful pop-art style, wide banner",
    "breaking-bad-quiz": "a desert chemistry laboratory silhouette at sunset, yellow hazmat-suit colors, glassware, moody cinematic desert tones, wide banner",
    "fireside-chats": "a cozy glowing campfire under a starry night sky, warm amber tones, intimate storytelling atmosphere, painterly illustration, wide banner",
    # --- standalone ---
    "rewind-2025": "a rewind play-button made of golden trophies and calendar pages flying back in time, celebratory fireworks, warm gold tones, wide banner",
    "kp-quiz-final": "a grand championship final stage with a glowing trophy under a spotlight, dramatic finale atmosphere, deep blue and gold tones, wide banner",
    "bollywood-kviz": "vibrant Bollywood cinema marquee lights behind a dramatic red curtain, colorful film-poster aesthetic, wide banner",
    "buzzer-bhide": "dynamic sports stadium silhouette with a glowing buzzer button, energetic action lines, vibrant team colors, wide banner",
    "tapish-sports": "collage of sports equipment — footballs, basketballs, cricket bats — dynamic action composition, vibrant stadium colors, wide banner",
    "history-smit": "ancient scrolls, maps and classical architecture ruins, sepia and gold tones, scholarly historical illustration, wide banner",
    "kvizimals": "whimsical collage of wild animal silhouettes, savanna color palette, playful nature illustration, wide banner",
    "movie-kviz": "a classic film reel and clapperboard surrounded by spotlight beams, cinematic golden-hour tones, wide banner",
    "may-the-4th": "a deep-space nebula crossed by a glowing blade of light, cosmic sci-fi illustration, blues and purples, wide banner",
    "old-school-kp": "a vintage schoolroom chalkboard and stack of old books, nostalgic sepia tones, classic illustration, wide banner",
    "swine-clue": "a whimsical detective's magnifying glass over a farmyard silhouette, playful mystery illustration, warm earthy tones, wide banner",
    "visual-buzzing-bijal": "abstract colorful visual-puzzle pieces and eye icons, vibrant pop-art collage, wide banner",
    "yet-another-quiz": "colorful abstract illustration of quiz-night trivia, geometric patterns, warm tones, wide banner",
    "naman-avval-number": "a glowing golden number-one trophy on a podium with celebratory confetti, vibrant festive colors, wide banner",
    "popcorn-buzzing-aditi": "a giant bucket of popcorn spilling over under a cinema spotlight, warm movie-night colors, playful illustration, wide banner",
    "tension-gourav": "a suspenseful illustration of a ticking clock tangled in wires under dramatic red lighting, tense atmosphere, wide banner",
    "buzzy-mushkil-hai": "a playful illustration of a glowing buzzer button surrounded by question marks, humorous warm colors, wide banner",
    "qotd-100": "a giant golden number 100 made of confetti and sparkling lights, celebratory milestone illustration, wide banner",
    "retro-bollywood-sameer": "vintage retro Bollywood cinema poster aesthetic, warm sepia and red tones, classic film reel, wide banner",
    "general-quiz-smit-sep-2026": "eclectic collage of general-knowledge icons — globe, books, atoms, musical notes — rich jewel tones, painterly illustration, wide banner",
    "long-connect-gautam": "an intricate web of glowing connected dots and lines forming a puzzle, abstract network illustration, deep blue and gold tones, wide banner",
    "random-quiz-namrata-aug-2026": "a kaleidoscope of random colorful abstract shapes and symbols, playful eclectic illustration, wide banner",
    "india-independence-qotd-shreya": "historical Indian independence movement imagery, tricolor flag motifs, vintage watercolor illustration, warm earthy tones, wide banner",
    "india-quiz-smit-jul-2026": "a colorful stylized map of India with iconic landmark silhouettes, vibrant cultural illustration, warm tones, wide banner",
    "cricket-quiz-harsh": "a cricket stadium at golden hour with a bat-and-ball silhouette, dynamic sports illustration, warm green and gold tones, wide banner",
    "triwizard-tourney-aditi": "a magical tournament goblet with blue flames before an enchanted castle silhouette, mystical purple and gold tones, fantasy illustration, wide banner",
}


def main(force_id: str | None = None) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ids = [force_id] if force_id else list(BANNER_PROMPTS.keys())

    for deck_id in ids:
        prompt = BANNER_PROMPTS.get(deck_id)
        if not prompt:
            print(f"[{deck_id}] No curated prompt — skipping.")
            continue

        dest = OUTPUT_DIR / f"{deck_id}.jpg"
        if dest.exists() and not force_id:
            print(f"[{deck_id}] Already exists — skipping.")
            continue

        print(f"[{deck_id}] Prompt: {prompt[:80]}...")
        img_bytes = None
        max_attempts = 5
        for attempt in range(max_attempts):
            if attempt > 0:
                print(f"  Retrying (attempt {attempt + 1}/{max_attempts})...")
            try:
                candidate = generate(prompt, seed=random.randint(0, 2**31 - 1))
                if not candidate:
                    continue
                if is_censored_placeholder(candidate):
                    print("  Worker returned a CENSORED placeholder — discarding, retrying.")
                    continue
                img_bytes = candidate
                break
            except Exception as e:
                print(f"  Error: {e}")

        if img_bytes:
            dest.write_bytes(img_bytes)
            print(f"  Saved ({len(img_bytes) // 1024} KB) → {dest.relative_to(V2_DIR)}\n")
        else:
            print(f"  Failed after retries — skipping.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", metavar="ID", help="Regenerate a single banner even if it already exists")
    args = parser.parse_args()
    main(force_id=args.force)
