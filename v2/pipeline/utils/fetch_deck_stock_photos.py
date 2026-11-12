"""
Experimental: fetch a real, CC-licensed stock photo per deck (series or
standalone session) from Openverse, keyed by the deck's dominant question
topic, as an alternative to the existing AI-generated banners.

Writes into a SEPARATE directory (images/decks-stock/) from the existing
generated banners (images/decks/), which this script never touches, so the
current generated images stay exactly as they are. Also writes an
attribution manifest, since CC licenses require crediting the photographer.

Standalone script, not wired into pipeline.py (same pattern as
generate_deck_banners.py). Run manually from v2/pipeline/:
    python3 -m utils.fetch_deck_stock_photos
"""
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "visualizer" / "static" / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "visualizer" / "static" / "images" / "decks-stock"
ATTRIBUTION_PATH = DATA_DIR / "decks_stock_attribution.json"

# Short descriptive phrases per topic, tuned for Openverse relevance (a bare
# topic label like "Business" alone tends to return weak generic matches).
TOPIC_QUERY = {
    "history": "ancient history historical architecture",
    "science": "science laboratory experiment",
    "mathematics": "mathematics geometry numbers",
    "technology": "technology computer circuit",
    "sports": "sports stadium athlete",
    "geography": "world map landscape travel",
    "entertainment": "entertainment stage concert",
    "music": "music concert instrument",
    "cinema": "cinema film movie theater",
    "food_drink": "food cuisine restaurant",
    "art_culture": "art museum painting culture",
    "literature": "books library literature",
    "business": "business finance office",
    "etymology": "old dictionary language books",
    "mythology": "mythology ancient statue temple",
    "politics": "politics government parliament",
    "medicine": "medicine hospital doctor",
    "military": "military history soldiers",
    "religion": "religion temple worship",
    "linguistics": "language alphabet typography",
    "nature": "nature wildlife forest",
    "meme": "internet culture humor",
    "general": "trivia quiz knowledge",
}

HEADERS = {"User-Agent": "KVizzing-deck-banner-experiment/1.0 (non-commercial research tool)"}

# Quiz-boilerplate words that carry no visual meaning on their own, stripped
# from a deck's title before using it as a search query - keeps real content
# words ("Cricket", "Triwizard", "Harry Potter", "MTV", "Breaking Bad") so
# the photo is about the actual quiz, not just its dominant topic bucket.
TITLE_STOPWORDS = {
    "quiz", "kviz", "kvizzing", "tournament", "tourney", "qotd", "round",
    "final", "part", "edition", "session", "sessions", "deck", "old", "new",
    "the", "a", "an", "of", "and", "with", "for", "by", "on", "in", "at",
    "to", "vs", "is", "it", "this", "that",
}


def title_keywords(title: str) -> str:
    cleaned = re.sub(r"[:–—\-\(\)\[\]'\".,!?]", " ", title)
    words = [w for w in cleaned.split() if w.lower() not in TITLE_STOPWORDS and not w.isdigit()]
    return " ".join(words).strip()


def dominant_topic_for_deck(session_ids: set[str], questions: list[dict]) -> str:
    counts: Counter[str] = Counter()
    for q in questions:
        sess = q.get("session") or {}
        if sess.get("id") in session_ids:
            topics = (q.get("question") or {}).get("topics") or []
            if topics:
                counts[topics[0]] += 1
    counts.pop("general", None)
    if not counts:
        return "general"
    return counts.most_common(1)[0][0]


def fetch_openverse_candidates(query: str, page: int = 1, page_size: int = 20) -> list[dict]:
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode({
        "q": query,
        "license_type": "commercial",
        "page_size": page_size,
        "page": page,
        "mature": "false",
    })
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    return data.get("results", [])


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        dest.write_bytes(resp.read())


def main() -> None:
    decks = json.loads((DATA_DIR / "decks.json").read_text())
    questions = json.loads((DATA_DIR / "questions.json").read_text())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    attribution: dict[str, dict] = {}
    if ATTRIBUTION_PATH.exists():
        attribution = json.loads(ATTRIBUTION_PATH.read_text())

    entries: list[tuple[str, str, set[str]]] = []
    for s in decks.get("series", []):
        session_ids = {f"deck-{s['id']}-r{r['round']}" for r in s.get("rounds", [])}
        entries.append((s["id"], s["title"], session_ids))
    for s in decks.get("standalone", []):
        entries.append((s["id"], s["title"], {f"deck-{s['id']}"}))

    # Many decks share a dominant topic (most things default to "cinema" or
    # "general"), and always taking the #1 result for an identical query
    # meant every deck in a topic bucket got the exact same photo. Round-robin
    # through each topic's result pool, and track every chosen result's id
    # globally so no two decks - even across different topics - ever end up
    # with the same photo.
    used_ids: set[str] = set()
    used_index_by_topic: dict[str, int] = {}

    for deck_id, title, session_ids in entries:
        topic = dominant_topic_for_deck(session_ids, questions)
        topic_phrase = TOPIC_QUERY.get(topic, TOPIC_QUERY["general"])
        kw = title_keywords(title)
        # Lead with the deck's own title keywords (the specific, visual part)
        # and keep the topic phrase appended as grounding context, so a
        # title with no usable content words still gets a sensible query.
        query = f"{kw} {topic_phrase}".strip() if kw else topic_phrase
        idx = used_index_by_topic.get(topic, 0)
        used_index_by_topic[topic] = idx + 1
        print(f"{deck_id} ({title}) -> topic={topic} query={query!r} slot={idx}")

        chosen = None
        for page in (1, 2, 3):
            try:
                candidates = fetch_openverse_candidates(query, page=page)
            except Exception as e:
                print(f"  ! fetch failed: {e}")
                break
            if not candidates:
                break
            pool_idx = idx % len(candidates)
            ordered = candidates[pool_idx:] + candidates[:pool_idx]
            chosen = next((c for c in ordered if c["id"] not in used_ids), None)
            if chosen:
                break
        if not chosen and kw:
            # The title keywords may be too narrow/specific to have 60
            # results across 3 pages. Drop them and widen to the plain
            # topic phrase before giving up on relevance entirely.
            try:
                candidates = fetch_openverse_candidates(topic_phrase, page=1)
                chosen = next((c for c in candidates if c["id"] not in used_ids), None)
            except Exception as e:
                print(f"  ! fallback fetch failed: {e}")
        if not chosen:
            # Last resort: the "general" bucket in particular can run dry of
            # genuinely distinct commercial-license results. Borrow from
            # another topic's pool entirely rather than ever repeat a photo.
            for other_topic, other_query in TOPIC_QUERY.items():
                if other_topic == topic:
                    continue
                try:
                    candidates = fetch_openverse_candidates(other_query, page=1)
                except Exception:
                    continue
                chosen = next((c for c in candidates if c["id"] not in used_ids), None)
                if chosen:
                    break
        if not chosen:
            print("  ! no unused candidate found anywhere")
            continue
        used_ids.add(chosen["id"])
        dest = OUTPUT_DIR / f"{deck_id}.jpg"
        try:
            download(chosen["url"], dest)
        except Exception as e:
            print(f"  ! download failed: {e}")
            continue
        attribution[deck_id] = {
            "title": chosen.get("title"),
            "creator": chosen.get("creator"),
            "creator_url": chosen.get("creator_url"),
            "license": chosen.get("license"),
            "license_version": chosen.get("license_version"),
            "license_url": chosen.get("license_url"),
            "source_url": chosen.get("foreign_landing_url"),
            "topic": topic,
        }
        time.sleep(1)  # be polite to the free, keyless API

    ATTRIBUTION_PATH.write_text(json.dumps(attribution, indent=2))
    print(f"\nWrote {len(attribution)} images to {OUTPUT_DIR}")
    print(f"Attribution manifest: {ATTRIBUTION_PATH}")


if __name__ == "__main__":
    main()
