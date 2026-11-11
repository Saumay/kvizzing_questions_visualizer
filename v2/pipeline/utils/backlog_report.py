"""
Generate the per-date publishing backlog report.

For every calendar date from the first chat message to the last, reports:
  - whether source chat text is available (current raw export / archivist / v1)
  - whether the date has been extracted into questions.db
  - question count, media coverage, topic coverage, tags coverage, reactions coverage
  - a `fully_published` flag: extracted AND media/topic/tags all 100% (reactions
    excluded from the gate — it needs a WhatsApp device SQLite backup that may
    never be available, so it's tracked as an informational column only)

Also generates a per-session report (v2/session_backlog.csv): for each session,
the roll-up of its own questions' publish status, plus theme/background-image/
scores presence. None of theme/image/scores gate anything — they're tracked for
visibility only, per 2026-10-31 decision.

Also generates a per-deck report (v2/deck_tracking.csv): decks.json rounds/
standalone decks have a different lifecycle than chat days (fetch file ->
transcribe -> import), so they're tracked separately with their own columns:
file_extracted (slide file actually downloaded/mirrored to R2, not just a
known Drive/OneDrive link), file_known_not_fetched (we know a slide file
exists but haven't pulled it yet), video_extracted (recording link present),
json_extracted (candidate Q&A JSON written), questions_populated (question
count actually imported into questions.json).

Writes v2/backlog_tracking.csv + v2/session_backlog.csv + v2/deck_tracking.csv,
and regenerates all three tables in v2/BACKLOG.md.

Usage:
    python3 pipeline/utils/backlog_report.py
"""

from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

V2_DIR = Path(__file__).parent.parent.parent
APP_DIR = V2_DIR.parent

RAW_CHAT = V2_DIR / "data" / "raw" / "_chat.txt"
RAW_MEDIA_DIR = V2_DIR / "data" / "raw"
ARCHIVIST_DIR = APP_DIR / "akshay_kvizzing_archivist" / "kvizzing_archivist_v1"
ARCHIVIST_CHAT = ARCHIVIST_DIR / "raw_whatsapp_chats" / "_chat_031826_040326.txt"
ARCHIVIST_MEDIA_DIR = ARCHIVIST_DIR / "media_source_dir_04012026"
V1_CHAT = APP_DIR / "v1" / "_chat.txt"
DB_PATH = V2_DIR / "data" / "questions.db"
SESSIONS_JSON = V2_DIR / "visualizer" / "static" / "data" / "sessions.json"
SESSION_IMAGES_DIR = V2_DIR / "visualizer" / "static" / "images" / "sessions"
DECKS_JSON = V2_DIR / "visualizer" / "static" / "data" / "decks.json"
CANDIDATES_DIR = V2_DIR / "pipeline" / "deck_extraction" / "candidates"
CSV_OUT = V2_DIR / "backlog_tracking.csv"
SESSION_CSV_OUT = V2_DIR / "session_backlog.csv"
DECK_CSV_OUT = V2_DIR / "deck_tracking.csv"
BACKLOG_MD = V2_DIR / "BACKLOG.md"
# Mirrors for the standalone static dashboard at visualizer/static/extraction-status/ —
# kept alongside the repo-root CSVs so that dashboard stays current without a
# manual copy step whenever this script runs.
VISUALIZER_DATA_DIR = V2_DIR / "visualizer" / "static" / "data"
VISUALIZER_CSV_OUT = VISUALIZER_DATA_DIR / "backlog_tracking.csv"
VISUALIZER_SESSION_CSV_OUT = VISUALIZER_DATA_DIR / "session_backlog.csv"
VISUALIZER_DECK_CSV_OUT = VISUALIZER_DATA_DIR / "deck_tracking.csv"
VISUALIZER_META_OUT = VISUALIZER_DATA_DIR / "backlog_meta.json"

# Formats an extraction agent can actually read — mirrors import_deck_questions
# ._EXTRACTABLE_FORMATS. Duplicated here (not imported) to avoid this report
# depending on the import pipeline module for a one-line constant.
_DECK_EXTRACTABLE_FORMATS = {"pdf", "pptx"}

_CHAT_DATE_RE = re.compile(r"^\[(\d{1,2})/(\d{1,2})/(\d{2}),")
_FILE_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def chat_dates(path: Path) -> set[date]:
    if not path.exists():
        return set()
    out = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _CHAT_DATE_RE.match(line)
            if m:
                mo, da, yr = m.groups()
                out.add(date(2000 + int(yr), int(mo), int(da)))
    return out


def media_dates(dirpath: Path) -> set[date]:
    if not dirpath.is_dir():
        return set()
    out = set()
    for fn in os.listdir(dirpath):
        m = _FILE_DATE_RE.search(fn)
        if m:
            out.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return out


def _question_published(q: dict, topic: str | None) -> bool:
    """A single question counts as published: topic set, tags non-empty,
    and media matched (with a real URL) if media was expected."""
    if not topic or not q.get("tags"):
        return False
    if q.get("has_media"):
        media = q.get("media") or []
        if not media or not all(m.get("url") for m in media):
            return False
    return True


def generate_session_report() -> None:
    if not SESSIONS_JSON.exists():
        print(f"skip sessions: {SESSIONS_JSON} not found")
        return
    sessions = json.loads(SESSIONS_JSON.read_text())

    per_session: dict[str, dict] = {}
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT session_id, topic, payload FROM questions WHERE session_id IS NOT NULL"
        ).fetchall()
        conn.close()
        for sid, topic, payload in rows:
            s = per_session.setdefault(sid, {"count": 0, "published": 0, "low_conf": 0})
            payload_obj = json.loads(payload)
            q = payload_obj["question"]
            s["count"] += 1
            if _question_published(q, topic):
                s["published"] += 1
            if payload_obj.get("extraction_confidence") == "low":
                s["low_conf"] += 1

    have_images = set()
    if SESSION_IMAGES_DIR.is_dir():
        have_images = {f.rsplit(".", 1)[0] for f in os.listdir(SESSION_IMAGES_DIR)}

    rows_out = []
    for sess in sessions:
        sid = sess["id"]
        stats = per_session.get(sid, {"count": sess.get("question_count", 0), "published": 0, "low_conf": 0})
        count = stats["count"] or sess.get("question_count", 0)
        pct = round(100.0 * stats["published"] / count, 1) if count else 0.0
        low_conf_pct = round(100.0 * stats["low_conf"] / count, 1) if count else 0.0
        rows_out.append({
            "session_id": sid,
            "date": sess.get("date", ""),
            "quizmaster": sess.get("quizmaster", ""),
            "question_count": count,
            "questions_published_pct": pct,
            "theme_present": bool(sess.get("theme")),
            "image_present": sid in have_images,
            "scores_present": sess.get("scores") is not None,
            "low_conf_pct": low_conf_pct,
        })

    fieldnames = list(rows_out[0].keys()) if rows_out else []
    if fieldnames:
        VISUALIZER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        for out_path in (SESSION_CSV_OUT, VISUALIZER_SESSION_CSV_OUT):
            with open(out_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows_out)

    _append_session_table_md(rows_out)

    n = len(rows_out)
    n_full_q = sum(1 for r in rows_out if r["questions_published_pct"] == 100.0)
    n_image = sum(r["image_present"] for r in rows_out)
    n_theme = sum(r["theme_present"] for r in rows_out)
    n_scores = sum(r["scores_present"] for r in rows_out)
    print(f"{n} sessions | questions 100% published: {n_full_q} | "
          f"image: {n_image} | theme: {n_theme} | scores: {n_scores}")
    print(f"wrote {SESSION_CSV_OUT}")


def _append_session_table_md(rows_out: list[dict]) -> None:
    lines = ["| Session | Date | Quizmaster | Questions | Questions published % | Theme | Image | Scores | Low conf % |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows_out:
        lines.append(
            f"| {r['session_id']} | {r['date']} | {r['quizmaster']} | {r['question_count']} "
            f"| {r['questions_published_pct']}% "
            f"| {'yes' if r['theme_present'] else ''} "
            f"| {'yes' if r['image_present'] else ''} "
            f"| {'yes' if r['scores_present'] else ''} "
            f"| {r['low_conf_pct']}% |"
        )
    table_md = "\n".join(lines)
    marker = "## Sessions"

    content = BACKLOG_MD.read_text() if BACKLOG_MD.exists() else "# Data backlog tracking\n"
    idx = content.find(marker)
    if idx != -1:
        header_end = content.find("\n", idx) + 1
        next_section = content.find("\n## ", header_end)
        if next_section == -1:
            next_section = len(content)
        content = content[:header_end] + "\n" + table_md + "\n\n" + content[next_section:]
    else:
        content += f"\n\n{marker}\n\nNone of theme/image/scores block publishing — tracked for visibility only.\n\n{table_md}\n"
    BACKLOG_MD.write_text(content)


def generate_deck_report() -> None:
    if not DECKS_JSON.exists():
        print(f"skip decks: {DECKS_JSON} not found")
        return
    manifest = json.loads(DECKS_JSON.read_text())

    question_counts: dict[str, int] = {}
    if SESSIONS_JSON.exists():
        for sess in json.loads(SESSIONS_JSON.read_text()):
            question_counts[sess["id"]] = sess.get("question_count", 0)

    def _slide_file(files: list[dict]) -> dict | None:
        return next((f for f in files if f.get("format") in _DECK_EXTRACTABLE_FORMATS), None)

    def _recording_file(files: list[dict]) -> dict | None:
        return next((f for f in files if f.get("format") == "recording"), None)

    def _row(session_id: str, series_id: str | None, round_num: int | None,
             title: str, host: str | None, date_str: str, files: list[dict]) -> dict:
        slide = _slide_file(files)
        rec = _recording_file(files)
        return {
            "session_id": session_id,
            "series_id": series_id or "",
            "round": round_num if round_num is not None else "",
            "title": title,
            "host": host or "",
            "date": date_str,
            "file_extracted": bool(slide and slide.get("rel_path")),
            "file_known_not_fetched": bool(slide and not slide.get("rel_path")),
            "video_extracted": bool(rec and rec.get("url")),
            "json_extracted": (CANDIDATES_DIR / f"{session_id}.json").exists(),
            "questions_populated": question_counts.get(session_id, 0),
        }

    rows_out = []
    for series in manifest.get("series", []):
        for r in series["rounds"]:
            session_id = f'deck-{series["id"]}-r{r["round"]}'
            rows_out.append(_row(
                session_id, series["id"], r["round"], f'{series["title"]}: {r["title"]}',
                r.get("host"), r.get("date", ""), r["files"],
            ))
    for deck in manifest.get("standalone", []):
        session_id = f'deck-{deck["id"]}'
        rows_out.append(_row(
            session_id, None, None, deck["title"], deck.get("host"),
            deck.get("date", ""), deck["files"],
        ))

    fieldnames = list(rows_out[0].keys()) if rows_out else []
    if fieldnames:
        VISUALIZER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        for out_path in (DECK_CSV_OUT, VISUALIZER_DECK_CSV_OUT):
            with open(out_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows_out)

    _append_deck_table_md(rows_out)

    n = len(rows_out)
    n_file = sum(r["file_extracted"] for r in rows_out)
    n_known = sum(r["file_known_not_fetched"] for r in rows_out)
    n_video = sum(r["video_extracted"] for r in rows_out)
    n_json = sum(r["json_extracted"] for r in rows_out)
    n_populated = sum(1 for r in rows_out if r["questions_populated"])
    print(f"{n} decks | file fetched: {n_file} | file known, not fetched: {n_known} "
          f"| video: {n_video} | json extracted: {n_json} | questions populated: {n_populated}")
    print(f"wrote {DECK_CSV_OUT}")


def _append_deck_table_md(rows_out: list[dict]) -> None:
    lines = ["| Session | Date | Host | File | File known (not fetched) | Video | JSON | Questions |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows_out:
        lines.append(
            f"| {r['session_id']} | {r['date']} | {r['host']} "
            f"| {'yes' if r['file_extracted'] else ''} "
            f"| {'yes' if r['file_known_not_fetched'] else ''} "
            f"| {'yes' if r['video_extracted'] else ''} "
            f"| {'yes' if r['json_extracted'] else ''} "
            f"| {r['questions_populated']} |"
        )
    table_md = "\n".join(lines)
    marker = "## Decks"

    content = BACKLOG_MD.read_text() if BACKLOG_MD.exists() else "# Data backlog tracking\n"
    idx = content.find(marker)
    if idx != -1:
        header_end = content.find("\n", idx) + 1
        next_section = content.find("\n## ", header_end)
        if next_section == -1:
            next_section = len(content)
        content = content[:header_end] + "\n" + table_md + "\n\n" + content[next_section:]
    else:
        content += f"\n\n{marker}\n\nfile_known_not_fetched means a Drive/OneDrive link is known but the file hasn't been pulled into R2 yet.\n\n{table_md}\n"
    BACKLOG_MD.write_text(content)


def main() -> None:
    src_dates = chat_dates(RAW_CHAT) | chat_dates(ARCHIVIST_CHAT) | chat_dates(V1_CHAT)
    media_all = media_dates(RAW_MEDIA_DIR) | media_dates(ARCHIVIST_MEDIA_DIR)

    db_stats: dict[str, dict] = {}
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute("SELECT date, topic, payload FROM questions").fetchall()
        conn.close()
        for d, topic, payload in rows:
            s = db_stats.setdefault(
                d, {"count": 0, "media_expected": 0, "media_matched": 0,
                    "topic_filled": 0, "tags_filled": 0, "reactions_filled": 0,
                    "high_conf": 0, "low_conf": 0}
            )
            s["count"] += 1
            payload_obj = json.loads(payload)
            q = payload_obj["question"]
            if q.get("has_media"):
                s["media_expected"] += 1
                media = q.get("media") or []
                if media and all(m.get("url") for m in media):
                    s["media_matched"] += 1
            if topic:
                s["topic_filled"] += 1
            if q.get("tags"):
                s["tags_filled"] += 1
            if payload_obj.get("reactions"):
                s["reactions_filled"] += 1
            conf = payload_obj.get("extraction_confidence")
            if conf == "high":
                s["high_conf"] += 1
            elif conf == "low":
                s["low_conf"] += 1

    start = min(src_dates) if src_dates else date(2025, 9, 23)
    end = date.today()

    rows_out = []
    d = start
    while d <= end:
        iso = d.isoformat()
        source_available = d in src_dates
        stats = db_stats.get(iso)
        extracted = stats is not None
        media_present = d in media_all

        if stats and stats["count"] > 0:
            count = stats["count"]
            media_pct = (
                100.0 if stats["media_expected"] == 0
                else round(100.0 * stats["media_matched"] / stats["media_expected"], 1)
            )
            topic_pct = round(100.0 * stats["topic_filled"] / count, 1)
            tags_pct = round(100.0 * stats["tags_filled"] / count, 1)
            reactions_pct = round(100.0 * stats["reactions_filled"] / count, 1)
            high_conf_pct = round(100.0 * stats["high_conf"] / count, 1)
            low_conf_pct = round(100.0 * stats["low_conf"] / count, 1)
            fully_published = (
                extracted and media_pct == 100.0 and topic_pct == 100.0 and tags_pct == 100.0
            )
        else:
            count = 0
            media_pct = topic_pct = tags_pct = reactions_pct = 0.0
            high_conf_pct = low_conf_pct = 0.0
            fully_published = False

        rows_out.append({
            "date": iso,
            "source_available": source_available,
            "extracted": extracted,
            "question_count": count,
            "media_source_present": media_present,
            "media_pct": media_pct,
            "topic_pct": topic_pct,
            "tags_pct": tags_pct,
            "reactions_pct": reactions_pct,
            "high_conf_pct": high_conf_pct,
            "low_conf_pct": low_conf_pct,
            "fully_published": fully_published,
        })
        d += timedelta(days=1)

    fieldnames = list(rows_out[0].keys())
    VISUALIZER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for out_path in (CSV_OUT, VISUALIZER_CSV_OUT):
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows_out)

    _rewrite_backlog_md(rows_out)

    n = len(rows_out)
    n_extracted = sum(r["extracted"] for r in rows_out)
    n_published = sum(r["fully_published"] for r in rows_out)
    print(f"{n} days total | extracted: {n_extracted} | fully published: {n_published}")
    print(f"wrote {CSV_OUT}")
    print(f"wrote {BACKLOG_MD}")

    generate_session_report()
    generate_deck_report()


def _rewrite_backlog_md(rows_out: list[dict]) -> None:
    header_date = f"## Full per-day table ({rows_out[0]['date']} - {rows_out[-1]['date']})"
    lines = [header_date, "",
             "| Date | Source | Extracted | Questions | Media % | Topic % | Tags % | Reactions % | Low conf % | Published |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows_out:
        lines.append(
            f"| {r['date']} | {'yes' if r['source_available'] else 'NO'} "
            f"| {'yes' if r['extracted'] else 'pending'} | {r['question_count']} "
            f"| {r['media_pct']}% | {r['topic_pct']}% | {r['tags_pct']}% | {r['reactions_pct']}% "
            f"| {r['low_conf_pct']}% "
            f"| {'YES' if r['fully_published'] else ''} |"
        )
    table_md = "\n".join(lines)

    start_marker = "## Full per-day table"
    if BACKLOG_MD.exists():
        content = BACKLOG_MD.read_text()
        idx = content.find(start_marker)
        if idx != -1:
            next_section = content.find("\n## ", idx + len(start_marker))
            if next_section == -1:
                next_section = len(content)
            content = content[:idx] + table_md + "\n\n" + content[next_section:].lstrip("\n")
        else:
            content += f"\n\n{table_md}\n"
    else:
        content = f"# Data backlog tracking\n\n{table_md}\n"

    BACKLOG_MD.write_text(content)


if __name__ == "__main__":
    main()
