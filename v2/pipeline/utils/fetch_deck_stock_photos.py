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


def fetch_openverse_candidates(query: str) -> list[dict]:
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode({
        "q": query,
        "license_type": "commercial",
        "page_size": 5,
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

    for deck_id, title, session_ids in entries:
        topic = dominant_topic_for_deck(session_ids, questions)
        query = TOPIC_QUERY.get(topic, TOPIC_QUERY["general"])
        print(f"{deck_id} ({title}) -> topic={topic} query={query!r}")
        try:
            candidates = fetch_openverse_candidates(query)
        except Exception as e:
            print(f"  ! fetch failed: {e}")
            continue
        if not candidates:
            print("  ! no results")
            continue
        chosen = candidates[0]
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
