"""Tests for Stage 6 — Export."""

import json
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "schema"))

from stages.stage5_store import run as store_run, upsert_session_final_scores
from stages.stage6_export import (
    build_questions,
    build_sessions,
    build_stats,
    build_tags,
    build_members,
    split_discussion,
    write_discussion_files,
    run,
)
from stages.stage3_structure import structure
from schema import KVizzingQuestion, TopicCategory

BASE_CONFIG = {
    "stage3": {
        "difficulty": {
            "easy_max_wrong_attempts": 0,
            "medium_max_wrong_attempts": 3,
        }
    }
}

_BASE_CANDIDATE = {
    "question_timestamp": "2025-09-23T19:25:40Z",
    "question_text": "What economic principle was established by the repeal of the Corn Laws?",
    "question_asker": "Pavan",
    "has_media": False,
    "is_session_question": False,
    "session_quizmaster": None,
    "session_theme": None,
    "session_question_number": None,
    "answer_text": "Free trade",
    "answer_solver": "Aditi",
    "answer_timestamp": "2025-09-23T19:27:10Z",
    "answer_confirmed": True,
    "confirmation_text": "Bingo!",
    "answer_is_collaborative": False,
    "answer_parts": None,
    "discussion": [
        {"timestamp": "2025-09-23T19:26:01Z", "username": "Akshay", "text": "Tariffs?", "role": "attempt", "is_correct": False},
        {"timestamp": "2025-09-23T19:27:10Z", "username": "Aditi", "text": "Free trade!", "role": "attempt", "is_correct": True},
    ],
    "scores_after": None,
    "extraction_confidence": "high",
}


def _make_question(timestamp_offset: int = 0, **overrides) -> KVizzingQuestion:
    import copy
    from datetime import datetime, timezone, timedelta
    c = copy.deepcopy(_BASE_CANDIDATE)
    c.update(overrides)
    if timestamp_offset:
        base = datetime(2025, 9, 23, 19, 25, 40, tzinfo=timezone.utc)
        new_ts = (base + timedelta(seconds=timestamp_offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["question_timestamp"] = new_ts
        ans_ts = (base + timedelta(seconds=timestamp_offset + 90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["answer_timestamp"] = ans_ts
        c["discussion"] = [
            {"timestamp": ans_ts, "username": "Aditi", "text": "Free trade!", "role": "attempt", "is_correct": True},
        ]
    return structure(c, BASE_CONFIG, Counter())


def _make_session_question(
    timestamp_offset: int = 0,
    quizmaster: str = "pratik.s.chandarana",
    question_number: int = 1,
    scores_after=None,
) -> KVizzingQuestion:
    import copy
    from datetime import datetime, timezone, timedelta
    c = copy.deepcopy(_BASE_CANDIDATE)
    c["is_session_question"] = True
    c["session_quizmaster"] = quizmaster
    c["session_theme"] = "Movies"
    c["session_question_number"] = question_number
    if scores_after is not None:
        c["scores_after"] = scores_after
    if timestamp_offset:
        base = datetime(2025, 9, 23, 19, 25, 40, tzinfo=timezone.utc)
        new_ts = (base + timedelta(seconds=timestamp_offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["question_timestamp"] = new_ts
        ans_ts = (base + timedelta(seconds=timestamp_offset + 90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c["answer_timestamp"] = ans_ts
        c["discussion"] = [
            {"timestamp": ans_ts, "username": "Aditi", "text": "Free trade!", "role": "attempt", "is_correct": True},
        ]
    return structure(c, BASE_CONFIG, Counter())


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def db_with_questions(db):
    """DB pre-loaded with 2 ad-hoc + 5 session questions.
    build_sessions filters out sessions with < 5 questions, so we need 5
    to exercise the session export path."""
    q1 = _make_question(timestamp_offset=0)
    q2 = _make_question(timestamp_offset=200)
    session_questions = [
        _make_session_question(
            timestamp_offset=400 + 200 * i,
            question_number=i + 1,
            scores_after=[{"username": "Akshay", "score": i + 1}],
        )
        for i in range(5)
    ]
    all_questions = [q1, q2, *session_questions]
    store_run(all_questions, db)
    return db, all_questions


class TestBuildQuestions:
    def test_returns_all_questions(self, db_with_questions):
        db, questions = db_with_questions
        result = build_questions(db)
        assert len(result) == 7

    def test_sorted_by_timestamp(self, db_with_questions):
        db, _ = db_with_questions
        result = build_questions(db)
        timestamps = [q["question"]["timestamp"] for q in result]
        assert timestamps == sorted(timestamps)

    def test_scores_after_populated_for_session_questions(self, db_with_questions):
        db, questions = db_with_questions
        result = build_questions(db)
        session_qs = [q for q in result if q.get("session")]
        assert all(q["scores_after"] is not None for q in session_qs)

    def test_scores_after_null_for_adhoc(self, db_with_questions):
        db, _ = db_with_questions
        result = build_questions(db)
        adhoc_qs = [q for q in result if not q.get("session")]
        assert all(q["scores_after"] is None for q in adhoc_qs)

    def test_scores_after_values_correct(self, db_with_questions):
        db, questions = db_with_questions
        result = build_questions(db)
        sq1_result = next(q for q in result if q.get("session") and q["session"]["question_number"] == 1)
        assert sq1_result["scores_after"][0]["username"] == "Akshay"
        assert sq1_result["scores_after"][0]["score"] == 1

    def test_payload_fields_intact(self, db_with_questions):
        db, _ = db_with_questions
        result = build_questions(db)
        for q in result:
            assert "id" in q
            assert "question" in q
            assert "answer" in q
            assert "stats" in q


class TestBuildSessions:
    def test_returns_session_list(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert len(sessions) == 1
        assert sessions[0]["id"] == "2025-09-23-pratik"

    def test_question_count_correct(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["question_count"] == 5

    def test_quizmaster_populated(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["quizmaster"] == "pratik.s.chandarana"

    def test_theme_populated(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["theme"] == "Movies"

    def test_avg_stats_computed(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["avg_time_to_answer_seconds"] == 90.0
        assert sessions[0]["avg_wrong_attempts"] == 0.0

    def test_participant_count(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["participant_count"] == 1  # only Aditi attempts

    def test_final_scores_included(self, db_with_questions):
        db, _ = db_with_questions
        upsert_session_final_scores(
            "2025-09-23-pratik",
            [{"username": "Akshay", "score": 5}],
            db,
        )
        sessions = build_sessions(db)
        assert sessions[0]["scores"] is not None
        assert sessions[0]["scores"][0]["score"] == 5

    def test_no_final_scores_is_none(self, db_with_questions):
        db, _ = db_with_questions
        sessions = build_sessions(db)
        assert sessions[0]["scores"] is None

    def test_empty_db_returns_empty(self, db):
        store_run([], db)
        sessions = build_sessions(db)
        assert sessions == []


class TestBuildStats:
    def test_total_questions_count(self):
        q1 = json.loads(_make_question().model_dump_json())
        q2 = json.loads(_make_question(timestamp_offset=200).model_dump_json())
        stats = build_stats([q1, q2])
        assert stats["total_questions"] == 2

    def test_total_sessions_count(self, db_with_questions):
        db, _ = db_with_questions
        questions = build_questions(db)
        stats = build_stats(questions)
        assert stats["total_sessions"] == 1

    def test_topic_distribution(self):
        q = json.loads(_make_question().model_dump_json())
        q["question"]["topics"] = ["history"]
        stats = build_stats([q])
        assert stats["topic_distribution"]["history"] == 1

    def test_difficulty_distribution(self):
        q = json.loads(_make_question().model_dump_json())
        q["stats"]["difficulty"] = "easy"
        stats = build_stats([q])
        assert stats["difficulty_distribution"]["easy"] == 1

    def test_session_activity_by_date(self, db_with_questions):
        db, _ = db_with_questions
        questions = build_questions(db)
        stats = build_stats(questions)
        assert len(stats["session_activity"]) >= 1
        entry = stats["session_activity"][0]
        assert "date" in entry
        assert "question_count" in entry

    def test_empty_input(self):
        stats = build_stats([])
        assert stats["total_questions"] == 0
        assert stats["total_sessions"] == 0


class TestBuildTags:
    def test_tag_index_built(self):
        q = json.loads(_make_question().model_dump_json())
        q["question"]["tags"] = ["economics", "uk"]
        tags = build_tags([q])
        economics = next((t for t in tags if t["tag"] == "economics"), None)
        assert economics is not None
        assert q["id"] in economics["question_ids"]

    def test_multiple_questions_same_tag(self):
        q1 = json.loads(_make_question().model_dump_json())
        q2 = json.loads(_make_question(timestamp_offset=200).model_dump_json())
        q1["question"]["tags"] = ["history"]
        q2["question"]["tags"] = ["history"]
        tags = build_tags([q1, q2])
        history = next(t for t in tags if t["tag"] == "history")
        assert history["count"] == 2

    def test_no_tags_returns_empty(self):
        q = json.loads(_make_question().model_dump_json())
        q["question"]["tags"] = []
        assert build_tags([q]) == []

    def test_empty_input(self):
        assert build_tags([]) == []


class TestBuildMembers:
    def test_asker_counted(self):
        q = json.loads(_make_question().model_dump_json())
        members = build_members([q], [])
        pavan = next(m for m in members if m["username"] == "Pavan")
        assert pavan["questions_asked"] == 1

    def test_solver_counted(self):
        q = json.loads(_make_question().model_dump_json())
        members = build_members([q], [])
        aditi = next(m for m in members if m["username"] == "Aditi")
        assert aditi["questions_solved"] == 1

    def test_attempts_counted(self):
        q = json.loads(_make_question().model_dump_json())
        members = build_members([q], [])
        akshay = next((m for m in members if m["username"] == "Akshay"), None)
        assert akshay is not None
        assert akshay["total_attempts"] == 1

    def test_config_display_name_applied(self):
        q = json.loads(_make_question().model_dump_json())
        config = [{"username": "Pavan", "display_name": "Pavan P", "color": "#FF0000", "avatar_url": None}]
        members = build_members([q], config)
        pavan = next(m for m in members if m["username"] == "Pavan")
        assert pavan["display_name"] == "Pavan P"
        assert pavan["color"] == "#FF0000"

    def test_unknown_member_gets_username_as_display_name(self):
        q = json.loads(_make_question().model_dump_json())
        members = build_members([q], [])
        pavan = next(m for m in members if m["username"] == "Pavan")
        assert pavan["display_name"] == "Pavan"
        assert pavan["color"] is None

    def test_avg_solve_time_computed(self):
        q = json.loads(_make_question().model_dump_json())
        members = build_members([q], [])
        aditi = next(m for m in members if m["username"] == "Aditi")
        assert aditi["avg_solve_time_seconds"] == 90.0

    def test_sessions_hosted_counted(self, db_with_questions):
        db, _ = db_with_questions
        questions = build_questions(db)
        members = build_members(questions, [])
        pratik = next(m for m in members if m["username"] == "pratik.s.chandarana")
        assert pratik["sessions_hosted"] == 1


class TestSplitDiscussion:
    def test_inline_subset_keeps_only_hint_and_answer_reveal(self):
        q = json.loads(_make_question().model_dump_json())
        q["discussion"] = [
            {"timestamp": "t1", "username": "A", "text": "attempt", "role": "attempt", "is_correct": False, "has_media": False, "media": None},
            {"timestamp": "t2", "username": "B", "text": "hint", "role": "hint", "is_correct": None, "has_media": False, "media": None},
            {"timestamp": "t3", "username": "C", "text": "reveal", "role": "answer_reveal", "is_correct": None, "has_media": False, "media": None},
        ]
        index_questions, discussion_by_id = split_discussion([q])
        roles = [e["role"] for e in index_questions[0]["discussion"]]
        assert roles == ["hint", "answer_reveal"]

    def test_discussion_count_is_full_length(self):
        q = json.loads(_make_question().model_dump_json())
        q["discussion"] = [
            {"timestamp": "t1", "username": "A", "text": "x", "role": "attempt", "is_correct": False, "has_media": False, "media": None},
            {"timestamp": "t2", "username": "B", "text": "y", "role": "chat", "is_correct": None, "has_media": False, "media": None},
        ]
        index_questions, _ = split_discussion([q])
        assert index_questions[0]["discussion_count"] == 2

    def test_full_discussion_keyed_by_id_when_extra_entries_exist(self):
        q = json.loads(_make_question().model_dump_json())
        q["discussion"] = [
            {"timestamp": "t1", "username": "A", "text": "x", "role": "attempt", "is_correct": False, "has_media": False, "media": None},
        ]
        index_questions, discussion_by_id = split_discussion([q])
        assert discussion_by_id[q["id"]] == q["discussion"]

    def test_no_file_needed_when_only_inline_roles_present(self):
        q = json.loads(_make_question().model_dump_json())
        q["discussion"] = [
            {"timestamp": "t1", "username": "A", "text": "hint", "role": "hint", "is_correct": None, "has_media": False, "media": None},
        ]
        _, discussion_by_id = split_discussion([q])
        assert q["id"] not in discussion_by_id

    def test_original_questions_list_untouched(self):
        q = json.loads(_make_question().model_dump_json())
        original_discussion = list(q["discussion"])
        split_discussion([q])
        assert q["discussion"] == original_discussion

    def test_write_discussion_files_writes_one_file_per_id(self):
        q1 = json.loads(_make_question().model_dump_json())
        q2 = json.loads(_make_question(timestamp_offset=200).model_dump_json())
        discussion_by_id = {q1["id"]: q1["discussion"], q2["id"]: q2["discussion"]}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            count = write_discussion_files(discussion_by_id, output_dir)
            assert count == 2
            assert (output_dir / "discussion" / f"{q1['id']}.json").exists()
            data = json.loads((output_dir / "discussion" / f"{q1['id']}.json").read_text())
            assert data == q1["discussion"]


class TestRun:
    def test_creates_all_json_files(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run(db, output_dir)
            assert (output_dir / "questions.json").exists()
            assert (output_dir / "sessions.json").exists()
            assert (output_dir / "stats.json").exists()
            assert (output_dir / "tags.json").exists()
            assert (output_dir / "members.json").exists()

    def test_questions_json_is_valid(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run(db, output_dir)
            data = json.loads((output_dir / "questions.json").read_text())
            assert isinstance(data, list)
            assert len(data) == 7

    def test_questions_json_discussion_trimmed_to_inline_roles(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run(db, output_dir)
            data = json.loads((output_dir / "questions.json").read_text())
            for q in data:
                assert all(e["role"] in ("hint", "answer_reveal") for e in q["discussion"])
                assert "discussion_count" in q

    def test_discussion_files_written_for_questions_with_attempts(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            run(db, output_dir)
            # every fixture question has "attempt" entries, none have hint/answer_reveal,
            # so every one should get a discussion file
            disc_dir = output_dir / "discussion"
            assert disc_dir.exists()
            assert len(list(disc_dir.glob("*.json"))) == 7

    def test_state_file_updated(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            state_path = output_dir / "pipeline_state.json"
            run(db, output_dir, state_path=state_path)
            state = json.loads(state_path.read_text())
            assert state["last_exported_date"] == "2025-09-23"

    def test_returns_counts(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            counts = run(db, Path(tmpdir))
            assert counts["questions"] == 7
            assert counts["sessions"] == 1

    def test_members_config_used(self, db_with_questions):
        db, _ = db_with_questions
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            members_config = [{"username": "Pavan", "display_name": "Pavan P", "color": "#F00", "avatar_url": None}]
            cfg_path = output_dir / "members.json.config"
            cfg_path.write_text(json.dumps(members_config))
            run(db, output_dir, members_config_path=cfg_path)
            members = json.loads((output_dir / "members.json").read_text())
            pavan = next(m for m in members if m["username"] == "Pavan")
            assert pavan["display_name"] == "Pavan P"
