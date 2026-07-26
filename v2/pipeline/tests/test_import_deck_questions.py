"""Tests for deck Q&A import (utils/import_deck_questions.py)."""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "schema"))

from stages.stage5_store import init_db
from utils.import_deck_questions import (
    candidates_from_pairs,
    derive_deck_sessions,
    ensure_session_thumbnail,
    import_all_available,
    import_file,
)


def _write_manifest(tmpdir: Path, manifest: dict) -> Path:
    path = tmpdir / "decks.json"
    path.write_text(json.dumps(manifest))
    return path


class TestDeriveDeckSessions:
    def test_series_round_with_pdf_included(self):
        manifest = {
            "series": [{
                "id": "gauntlet", "title": "The Gauntlet",
                "rounds": [{
                    "round": 1, "title": "Round One", "host": "Sal", "date": "2026-04-05",
                    "files": [{"format": "pdf", "rel_path": "g1.pdf"}],
                }],
            }],
            "standalone": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_manifest(Path(tmpdir), manifest)
            sessions = derive_deck_sessions(path)
        assert len(sessions) == 1
        s = sessions[0]
        assert s["session_id"] == "deck-gauntlet-r1"
        assert s["theme"] == "The Gauntlet: Round One"
        assert s["quizmaster"] == "Sal"
        assert s["date"] == "2026-04-05"

    def test_recording_only_round_skipped(self):
        manifest = {
            "series": [{
                "id": "gauntlet", "title": "The Gauntlet",
                "rounds": [{
                    "round": 1, "title": "No Slides", "host": "Sal", "date": "2026-04-05",
                    "files": [{"format": "recording", "rel_path": None}],
                }],
            }],
            "standalone": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_manifest(Path(tmpdir), manifest)
            sessions = derive_deck_sessions(path)
        assert sessions == []

    def test_pptx_only_round_skipped(self):
        manifest = {
            "series": [{
                "id": "gauntlet", "title": "The Gauntlet",
                "rounds": [{
                    "round": 1, "title": "Pptx Only", "host": "Vats", "date": "2026-04-15",
                    "files": [{"format": "pptx", "rel_path": "g6.pptx"}],
                }],
            }],
            "standalone": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_manifest(Path(tmpdir), manifest)
            sessions = derive_deck_sessions(path)
        assert sessions == []

    def test_round_with_both_pdf_and_pptx_uses_pdf(self):
        manifest = {
            "series": [{
                "id": "gauntlet", "title": "The Gauntlet",
                "rounds": [{
                    "round": 14, "title": "Both Formats", "host": "Lzafeer", "date": "2026-05-23",
                    "files": [
                        {"format": "pdf", "rel_path": "g14.pdf"},
                        {"format": "pptx", "rel_path": "g14.pptx"},
                    ],
                }],
            }],
            "standalone": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_manifest(Path(tmpdir), manifest)
            sessions = derive_deck_sessions(path)
        assert len(sessions) == 1
        assert sessions[0]["rel_path"] == "g14.pdf"

    def test_standalone_deck_session_id_and_theme(self):
        manifest = {
            "series": [],
            "standalone": [{
                "id": "movie-kviz", "title": "Movie Kviz", "host": None, "date": "2025-12-07",
                "files": [{"format": "pdf", "rel_path": "MOVIE KVIZ.pdf"}],
            }],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_manifest(Path(tmpdir), manifest)
            sessions = derive_deck_sessions(path)
        assert len(sessions) == 1
        s = sessions[0]
        assert s["session_id"] == "deck-movie-kviz"
        assert s["theme"] == "Movie Kviz"
        assert s["quizmaster"] is None

    def test_multiple_rounds_same_host_same_date_get_distinct_session_ids(self):
        # KVIZ-O-KRAZZY: all 7 rounds are Sal, same date — must stay distinct sessions.
        manifest = {
            "series": [{
                "id": "kviz-o-krazzy", "title": "KVIZ-O-KRAZZY",
                "rounds": [
                    {"round": 1, "title": "Q1", "host": "Sal", "date": "2026-04-15",
                     "files": [{"format": "pdf", "rel_path": "q1.pdf"}]},
                    {"round": 2, "title": "Q2", "host": "Sal", "date": "2026-04-15",
                     "files": [{"format": "pdf", "rel_path": "q2.pdf"}]},
                ],
            }],
            "standalone": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_manifest(Path(tmpdir), manifest)
            sessions = derive_deck_sessions(path)
        ids = {s["session_id"] for s in sessions}
        assert ids == {"deck-kviz-o-krazzy-r1", "deck-kviz-o-krazzy-r2"}


class TestCandidatesFromPairs:
    def test_timestamps_synthesized_two_minutes_apart(self):
        pairs = [
            {"question_text": "Q1", "answer_text": "A1"},
            {"question_text": "Q2", "answer_text": "A2"},
        ]
        candidates = candidates_from_pairs(
            pairs, session_id="deck-test", quizmaster="Sal", theme="Test", date="2026-01-01"
        )
        assert candidates[0]["question_timestamp"] == "2026-01-01T10:00:00Z"
        assert candidates[1]["question_timestamp"] == "2026-01-01T10:02:00Z"

    def test_session_id_override_and_question_number_set(self):
        pairs = [{"question_text": "Q1", "answer_text": "A1"}]
        candidates = candidates_from_pairs(
            pairs, session_id="deck-test-r3", quizmaster="Sal", theme="Test", date="2026-01-01"
        )
        assert candidates[0]["session_id_override"] == "deck-test-r3"
        assert candidates[0]["session_question_number"] == 1

    def test_no_host_falls_back_to_unknown_asker_but_keeps_quizmaster_none(self):
        pairs = [{"question_text": "Q1", "answer_text": "A1"}]
        candidates = candidates_from_pairs(
            pairs, session_id="deck-test", quizmaster=None, theme="Test", date="2026-01-01"
        )
        assert candidates[0]["question_asker"] == "unknown"
        assert candidates[0]["session_quizmaster"] is None

    def test_no_solver_no_discussion_answer_confirmed(self):
        pairs = [{"question_text": "Q1", "answer_text": "A1"}]
        candidates = candidates_from_pairs(
            pairs, session_id="deck-test", quizmaster="Sal", theme="Test", date="2026-01-01"
        )
        c = candidates[0]
        assert c["answer_solver"] is None
        assert c["discussion"] == []
        assert c["answer_confirmed"] is True

    def test_extraction_confidence_passthrough(self):
        pairs = [{"question_text": "Q1", "answer_text": "A1", "extraction_confidence": "medium"}]
        candidates = candidates_from_pairs(
            pairs, session_id="deck-test", quizmaster="Sal", theme="Test", date="2026-01-01"
        )
        assert candidates[0]["extraction_confidence"] == "medium"


class TestImportFileAndAllAvailable:
    @pytest.fixture
    def db(self):
        conn = sqlite3.connect(":memory:")
        yield conn
        conn.close()

    def test_import_file_stores_all_pairs(self, db):
        init_db(db)
        pairs = [
            {"question_text": "Q1", "answer_text": "A1", "extraction_confidence": "high"},
            {"question_text": "Q2", "answer_text": "A2", "extraction_confidence": "high"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "deck-test.json"
            path.write_text(json.dumps(pairs))
            from collections import Counter
            stored, failed = import_file(
                path, session_id="deck-test", quizmaster="Sal", theme="Test",
                date="2026-01-01", conn=db, collision_counter=Counter(),
            )
        assert stored == 2
        assert failed == 0

    def test_import_all_available_skips_sessions_without_candidate_file(self, db):
        manifest = {
            "series": [],
            "standalone": [{
                "id": "no-candidates-yet", "title": "Not Extracted", "host": "Sal", "date": "2026-01-01",
                "files": [{"format": "pdf", "rel_path": "x.pdf"}],
            }],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            manifest_path = _write_manifest(tmpdir_path, manifest)
            empty_candidates_dir = tmpdir_path / "candidates"
            empty_candidates_dir.mkdir()
            counts = import_all_available(db, manifest_path, candidates_dir=empty_candidates_dir)
        assert counts == {
            "decks_imported": 0, "decks_skipped": 1,
            "questions_stored": 0, "questions_failed": 0,
        }

    def test_import_all_available_imports_ready_deck(self, db):
        manifest = {
            "series": [],
            "standalone": [{
                "id": "ready-deck", "title": "Ready Deck", "host": "Sal", "date": "2026-01-01",
                "files": [{"format": "pdf", "rel_path": "x.pdf"}],
            }],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            manifest_path = _write_manifest(tmpdir_path, manifest)
            candidates_dir = tmpdir_path / "candidates"
            candidates_dir.mkdir()
            (candidates_dir / "deck-ready-deck.json").write_text(json.dumps([
                {"question_text": "Q1", "answer_text": "A1", "extraction_confidence": "high"},
            ]))
            counts = import_all_available(db, manifest_path, candidates_dir=candidates_dir)
        assert counts["decks_imported"] == 1
        assert counts["decks_skipped"] == 0
        assert counts["questions_stored"] == 1

    def test_running_twice_upserts_not_duplicates(self, db):
        manifest = {
            "series": [],
            "standalone": [{
                "id": "idempotent-deck", "title": "Idempotent", "host": "Sal", "date": "2026-01-01",
                "files": [{"format": "pdf", "rel_path": "x.pdf"}],
            }],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            manifest_path = _write_manifest(tmpdir_path, manifest)
            candidates_dir = tmpdir_path / "candidates"
            candidates_dir.mkdir()
            (candidates_dir / "deck-idempotent-deck.json").write_text(json.dumps([
                {"question_text": "Q1", "answer_text": "A1", "extraction_confidence": "high"},
            ]))
            import_all_available(db, manifest_path, candidates_dir=candidates_dir)
            import_all_available(db, manifest_path, candidates_dir=candidates_dir)
            row_count = db.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        assert row_count == 1


class TestEnsureSessionThumbnail:
    def test_skips_if_already_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            images_dir = Path(tmpdir)
            existing = images_dir / "deck-test.jpg"
            existing.write_bytes(b"not a real jpg, just needs to exist")
            result = ensure_session_thumbnail(
                "some/deck.pdf", "deck-test", images_dir=images_dir, quiz_decks_dir=images_dir
            )
            assert result is True
            assert existing.read_bytes() == b"not a real jpg, just needs to exist"

    def test_non_pdf_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            images_dir = Path(tmpdir) / "images"
            result = ensure_session_thumbnail(
                "some/deck.pptx", "deck-test", images_dir=images_dir, quiz_decks_dir=Path(tmpdir)
            )
        assert result is False
        assert not (images_dir / "deck-test.jpg").exists()

    def test_missing_pdf_returns_false_without_raising(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            images_dir = Path(tmpdir) / "images"
            result = ensure_session_thumbnail(
                "does/not/exist.pdf", "deck-test", images_dir=images_dir, quiz_decks_dir=Path(tmpdir)
            )
        assert result is False
