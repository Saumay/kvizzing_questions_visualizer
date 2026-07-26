"""
Import extracted deck Q&A candidate JSON files into questions.db, reusing
the existing structure()/upsert() pipeline stages so downstream export
(questions.json, discussion split, embeddings — all wired into stage6)
just works unchanged.

Two-step workflow, since the actual slide-reading has to be done by an LLM
(text-heuristic extraction doesn't hold across decks — formats vary too
much, and many question slides are pure images with no extractable text):

  1. Extraction (manual/agent-driven, not scriptable): read a deck's PDF
     via an agent with vision-capable Read access, transcribe each
     question/answer slide pair, write the result to
     deck_extraction/candidates/deck-<session_id>.json as a JSON array:
       [{"question_text": str, "answer_text": str, "has_media": bool,
         "extraction_confidence": "high"|"medium"}, ...]

  2. Import (this module, fully automated): derive_deck_sessions() walks
     decks.json for every round/standalone deck that has an actual slide
     file (pdf/pptx/docx — skips recording-only entries, there's nothing to
     extract from a video link), matches each to its candidate file if one
     exists yet, and imports whatever's available. Re-running is safe and
     incremental — sessions without a candidate file yet are skipped, not
     errored, so this can be run again as more decks get extracted over
     time. Run via `python3 pipeline.py import-decks`.

Deck questions have no chat timestamps to anchor an id to, so this
synthesizes one: session date + (question_number * 2 minutes). That keeps
the existing YYYY-MM-DD-HHMMSS id format working unmodified everywhere else
(discussion file naming, embeddings meta, sort order) without any
special-casing. session_id_override is set explicitly per deck/round
because several decks share the same host on the same synthesized date
(e.g. all 7 KVIZ-O-KRAZZY rounds are "Sal" on the same day) — without the
override, structure()'s default `date-quizmaster_slug` session id would
collapse them into one session.

No solver, no discussion, no wrong-attempt stats: decks are static slides,
not a tracked live chat, so there's no "who got it right first" data to
capture. answer_confirmed=True since the slide IS the canonical answer key,
not something needing chat confirmation.

Known gap (not handled yet): question/answer slide images aren't extracted
or uploaded anywhere — has_media reflects whether the source slide had an
essential image, but media itself is None, so those cards render without a
picture until a follow-up pass adds image extraction + R2 upload.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "schema"))

from stages.stage3_structure import structure  # noqa: E402
from stages.stage5_store import init_db, upsert  # noqa: E402

BASE_CONFIG = {
    "stage3": {
        "difficulty": {"easy_max_wrong_attempts": 0, "medium_max_wrong_attempts": 3},
    }
}

CANDIDATES_DIR = Path(__file__).parent.parent / "deck_extraction" / "candidates"
QUIZ_DECKS_DIR = Path(__file__).parent.parent.parent.parent / "quiz_decks"
SESSION_IMAGES_DIR = Path(__file__).parent.parent.parent / "visualizer" / "static" / "images" / "sessions"

# Formats an extraction agent can actually read. PPTX can't be read directly
# (binary, no LibreOffice available to render it) — those decks are skipped
# here until a PPTX image/text extraction path exists.
_EXTRACTABLE_FORMATS = {"pdf"}


def derive_deck_sessions(decks_manifest_path: Path) -> list[dict]:
    """
    Walk decks.json and return one entry per round/standalone deck that has
    an actual extractable slide file — skips recording-only entries (no
    file to extract from) and non-extractable formats (pptx, docx).

    Each entry: {session_id, quizmaster, theme, date, candidate_path,
    rel_path} — candidate_path points to where the extracted JSON is
    expected, whether or not it exists yet.
    """
    manifest = json.loads(decks_manifest_path.read_text())
    sessions = []

    def _extractable_file(files: list[dict]) -> dict | None:
        for f in files:
            if f.get("format") in _EXTRACTABLE_FORMATS and f.get("rel_path"):
                return f
        return None

    for series in manifest.get("series", []):
        for round_ in series["rounds"]:
            f = _extractable_file(round_["files"])
            if not f:
                continue
            session_id = f'deck-{series["id"]}-r{round_["round"]}'
            sessions.append({
                "session_id": session_id,
                "quizmaster": round_.get("host"),
                "theme": f'{series["title"]}: {round_["title"]}',
                "date": round_["date"],
                "rel_path": f["rel_path"],
                "candidate_path": CANDIDATES_DIR / f"{session_id}.json",
            })

    for deck in manifest.get("standalone", []):
        f = _extractable_file(deck["files"])
        if not f:
            continue
        session_id = f'deck-{deck["id"]}'
        sessions.append({
            "session_id": session_id,
            "quizmaster": deck.get("host"),
            "theme": deck["title"],
            "date": deck["date"],
            "rel_path": f["rel_path"],
            "candidate_path": CANDIDATES_DIR / f"{session_id}.json",
        })

    return sessions


def candidates_from_pairs(
    pairs: list[dict],
    *,
    session_id: str,
    quizmaster: str | None,
    theme: str,
    date: str,
) -> list[dict]:
    """Map extracted {question_text, answer_text, ...} pairs to stage3 candidate dicts."""
    base_dt = datetime.fromisoformat(f"{date}T10:00:00+00:00")
    out = []
    for i, pair in enumerate(pairs, start=1):
        q_ts = (base_dt + timedelta(minutes=2 * (i - 1))).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({
            "question_timestamp": q_ts,
            "question_text": pair["question_text"],
            "question_asker": quizmaster or "unknown",
            "has_media": bool(pair.get("has_media", False)),
            "is_session_question": True,
            "session_quizmaster": quizmaster,
            "session_theme": theme,
            "session_question_number": i,
            "session_id_override": session_id,
            "session_is_live": True,
            "answer_text": pair.get("answer_text"),
            "answer_solver": None,
            "answer_timestamp": None,
            "answer_confirmed": True,
            "confirmation_text": None,
            "answer_is_collaborative": False,
            "answer_parts": None,
            "discussion": [],
            "extraction_confidence": pair.get("extraction_confidence", "medium"),
        })
    return out


def ensure_session_thumbnail(
    rel_path: str,
    session_id: str,
    images_dir: Path = SESSION_IMAGES_DIR,
    quiz_decks_dir: Path = QUIZ_DECKS_DIR,
    page_number: int = 0,
) -> bool:
    """
    Render a deck's title slide as its session card thumbnail, at
    images_dir/<session_id>.jpg — the exact path the frontend already looks
    up for every session (see sessionBgUrl in lib/config/ui.ts), so no
    frontend change is needed. Only PDFs are supported (matches the
    extraction path). Skips if a thumbnail already exists. Returns True if
    a thumbnail exists afterward (already there, or just rendered).
    """
    out_path = images_dir / f"{session_id}.jpg"
    if out_path.exists():
        return True
    if not rel_path.lower().endswith(".pdf"):
        return False
    try:
        import fitz
        doc = fitz.open(quiz_decks_dir / rel_path)
        page = doc[page_number if page_number < doc.page_count else 0]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        images_dir.mkdir(parents=True, exist_ok=True)
        pix.save(str(out_path), jpg_quality=85)
        doc.close()
        return True
    except Exception as e:
        print(f"  thumbnail failed for {session_id}: {e}")
        return False


def import_file(
    path: Path,
    *,
    session_id: str,
    quizmaster: str | None,
    theme: str,
    date: str,
    conn: sqlite3.Connection,
    collision_counter: Counter,
) -> tuple[int, int]:
    """Structure + upsert one deck's candidate JSON file. Returns (stored_count, failed_count)."""
    pairs = json.loads(path.read_text())
    candidates = candidates_from_pairs(
        pairs, session_id=session_id, quizmaster=quizmaster, theme=theme, date=date
    )
    questions = []
    failed = 0
    for i, c in enumerate(candidates, start=1):
        try:
            q = structure(c, BASE_CONFIG, collision_counter, source_file=path.name, pair_index=i)
            questions.append(q)
        except ValueError as e:
            print(f"  FAILED pair {i} in {path.name}: {e}")
            failed += 1
    stored = upsert(questions, conn)
    return stored, failed


def import_all_available(
    conn: sqlite3.Connection,
    decks_manifest_path: Path,
    candidates_dir: Path = CANDIDATES_DIR,
) -> dict[str, int]:
    """
    Import every deck session that has a candidate file ready. Sessions
    without one yet are skipped (not an error) — that's the normal state
    for decks not extracted yet.
    """
    init_db(conn)
    collision_counter: Counter = Counter()
    sessions = derive_deck_sessions(decks_manifest_path)

    imported = skipped = total_stored = total_failed = 0
    for s in sessions:
        candidate_path = candidates_dir / f'{s["session_id"]}.json'
        if not candidate_path.exists():
            skipped += 1
            continue
        stored, failed = import_file(
            candidate_path,
            session_id=s["session_id"],
            quizmaster=s["quizmaster"],
            theme=s["theme"],
            date=s["date"],
            conn=conn,
            collision_counter=collision_counter,
        )
        print(f'{s["session_id"]}: stored {stored}, failed {failed}')
        imported += 1
        total_stored += stored
        total_failed += failed
        ensure_session_thumbnail(s["rel_path"], s["session_id"])

    print(
        f"\n{imported} deck(s) imported ({total_stored} questions, {total_failed} failed), "
        f"{skipped} deck(s) skipped (no candidate file yet)"
    )
    return {
        "decks_imported": imported,
        "decks_skipped": skipped,
        "questions_stored": total_stored,
        "questions_failed": total_failed,
    }
