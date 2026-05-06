"""
Scan rejected_candidates files for clusters of question-mark-ending messages
by the same user within a tight time window — these are likely missed sessions
that the LLM extractor skipped.

Pattern flagged: 3+ messages from the same user, all ending with '?', within
30 minutes (configurable), where each message is at least min_text_length chars.

Usage:
    python3 utils/audit_missed_sessions.py [--min-questions N] [--window-minutes M] [--min-length L]
    python3 utils/audit_missed_sessions.py --date 2025-11-03
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REJECTED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "attribution_gaps" / "rejected_candidates"


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.rstrip("Z"))


def find_clusters(
    threads: list[dict],
    min_questions: int = 3,
    window_minutes: float = 30.0,
    min_text_length: int = 80,
) -> list[dict]:
    """
    Flatten all candidates across threads, group by username, find dense clusters.
    Returns: [{username, count, first_ts, last_ts, samples: [{ts, text_preview}]}]
    """
    by_user: dict[str, list[tuple[datetime, str, str]]] = {}
    for thr in threads:
        for c in thr.get("candidates", []):
            text = (c.get("text") or "").strip()
            if not text.endswith("?"):
                continue
            if len(text) < min_text_length:
                continue
            try:
                ts = _parse_ts(c["timestamp"])
            except Exception:
                continue
            user = c.get("username", "")
            by_user.setdefault(user, []).append((ts, text, c["timestamp"]))

    clusters = []
    window = timedelta(minutes=window_minutes)
    for user, items in by_user.items():
        items.sort(key=lambda x: x[0])
        # sliding window
        i = 0
        while i < len(items):
            j = i
            while j + 1 < len(items) and items[j + 1][0] - items[i][0] <= window:
                j += 1
            cluster_size = j - i + 1
            if cluster_size >= min_questions:
                clusters.append({
                    "username": user,
                    "count": cluster_size,
                    "first_ts": items[i][2],
                    "last_ts": items[j][2],
                    "samples": [
                        {"ts": items[k][2], "preview": items[k][1][:120]}
                        for k in range(i, j + 1)
                    ],
                })
                i = j + 1
            else:
                i += 1
    return clusters


def audit_file(path: Path, **kwargs) -> list[dict]:
    try:
        threads = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return find_clusters(threads, **kwargs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Only check this date (YYYY-MM-DD); else scan all")
    ap.add_argument("--min-questions", type=int, default=3)
    ap.add_argument("--window-minutes", type=float, default=30.0)
    ap.add_argument("--min-length", type=int, default=80)
    ap.add_argument("--rejected-dir", default=str(REJECTED_DIR))
    args = ap.parse_args()

    rejected_dir = Path(args.rejected_dir)
    if not rejected_dir.exists():
        print(f"Rejected dir not found: {rejected_dir}", file=sys.stderr)
        return 1

    files = sorted(rejected_dir.glob(f"{args.date}.json" if args.date else "*.json"))
    if not files:
        print("No rejected files to scan.")
        return 0

    total_flagged = 0
    for f in files:
        clusters = audit_file(
            f,
            min_questions=args.min_questions,
            window_minutes=args.window_minutes,
            min_text_length=args.min_length,
        )
        if not clusters:
            continue
        date_str = f.stem
        for c in clusters:
            total_flagged += 1
            print(f"[{date_str}] {c['username']}: {c['count']} likely-missed Qs "
                  f"({c['first_ts']} → {c['last_ts']})")
            for s in c["samples"][:3]:
                print(f"    {s['ts']}: {s['preview']}")
            if len(c["samples"]) > 3:
                print(f"    … +{len(c['samples']) - 3} more")
    if total_flagged:
        print(f"\n{total_flagged} potential missed session(s) flagged.")
        return 1
    print("No missed-session clusters found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
