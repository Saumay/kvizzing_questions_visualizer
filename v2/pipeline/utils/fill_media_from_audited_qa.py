"""
Attach the real WhatsApp media filename (from Akshay's audited_qa export)
directly onto already-imported questions, bypassing enrich-media's timestamp-
window heuristic entirely — we have the ground-truth filename, no need to guess.

Akshay's audited_qa records carry media info in two different places: a
top-level `media[].filename`, which is HIS OWN re-rendered PDF asset name
(e.g. '2026-03-15_p002_m0001.jpeg') and never matches our raw export, and a
nested `source...media_files[].filename`, which is the real original WhatsApp
filename (e.g. '00248662-PHOTO-2026-03-15-00-01-10.jpg') — that's the one we
want. Its exact nesting path varies across the export's schema versions, so
we search for it recursively instead of hardcoding one path.

Matches an audited_qa record to a stored DB question by exact question text
within the same date (our import copied `question` text verbatim), falling
back to positional pairing within same-text groups (same strategy as the
import script, for duplicate-text bursts like repeated visual rounds).

Only ever sets `media` on a question that doesn't already have a real URL —
never overwrites a question enrich-media already matched correctly.

Usage:
    python3 utils/fill_media_from_audited_qa.py <audited_qa_dir> <date> [<date> ...]
"""

from __future__ import annotations

import json
import mimetypes
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent.parent
V2_DIR = PIPELINE_DIR.parent
RAW_MEDIA_DIR = V2_DIR / "data" / "raw"
DB_PATH = V2_DIR / "data" / "questions.db"

_EXT_TYPE = {
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image",
    ".mp4": "video", ".mov": "video",
    ".opus": "audio", ".mp3": "audio", ".m4a": "audio",
    ".pdf": "document", ".docx": "document",
}


def _media_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return _EXT_TYPE.get(ext, "image")


def _find_media_filenames(obj) -> list[str]:
    out: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("media_files"), list):
                for mf in o["media_files"]:
                    if isinstance(mf, dict) and mf.get("filename"):
                        out.append(mf["filename"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    # de-dup, keep order
    seen = set()
    uniq = []
    for f in out:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    audited_dir = Path(sys.argv[1])
    target_dates = set(sys.argv[2:])
    raw_files = set(f.name for f in RAW_MEDIA_DIR.iterdir() if f.is_file())

    # date -> list of (question_text, [real_filenames]), in audited_qa's own order
    audited_by_date: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for f in sorted(audited_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for rec in data:
            d = rec.get("date")
            if d not in target_dates or not rec.get("media"):
                continue
            filenames = [fn for fn in _find_media_filenames(rec) if fn in raw_files]
            if filenames:
                audited_by_date[d].append((rec.get("timestamp") or "", rec.get("question") or "", filenames))
        for d in audited_by_date:
            audited_by_date[d].sort(key=lambda t: t[0])

    conn = sqlite3.connect(str(DB_PATH))
    total_filled = 0
    for date_str in sorted(target_dates):
        rows = conn.execute(
            "SELECT id, payload FROM questions WHERE date = ?", (date_str,)
        ).fetchall()
        candidates = []
        for qid, payload_str in rows:
            p = json.loads(payload_str)
            q = p["question"]
            if not q.get("has_media"):
                continue
            media = q.get("media") or []
            if media and any(m.get("url") for m in media):
                continue  # already has a real uploaded file — leave alone
            candidates.append((q["timestamp"], qid, p))
        candidates.sort(key=lambda t: t[0])

        audited_recs = audited_by_date.get(date_str, [])
        # group both sides by exact question text, pair positionally within each group
        db_by_text: dict[str, list[tuple]] = defaultdict(list)
        for ts, qid, p in candidates:
            db_by_text[p["question"]["text"]].append((ts, qid, p))
        aud_by_text: dict[str, list[list[str]]] = defaultdict(list)
        for ts, text, filenames in audited_recs:
            aud_by_text[text].append(filenames)

        filled_this_date = 0
        for text, db_group in db_by_text.items():
            aud_group = aud_by_text.get(text)
            if not aud_group:
                continue
            for (ts, qid, p), filenames in zip(db_group, aud_group):
                p["question"]["media"] = [
                    {"type": _media_type(fn), "url": None, "filename": fn, "caption": None}
                    for fn in filenames
                ]
                conn.execute(
                    "UPDATE questions SET payload = ? WHERE id = ?",
                    (json.dumps(p, ensure_ascii=False), qid),
                )
                filled_this_date += 1
        if filled_this_date:
            print(f"  [{date_str}] attached media filename to {filled_this_date} question(s)")
        total_filled += filled_this_date

    conn.commit()
    conn.close()
    print(f"Total: {total_filled} questions got a real filename attached (still need upload-media to get URLs).")


if __name__ == "__main__":
    main()
