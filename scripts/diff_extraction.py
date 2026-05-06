#!/usr/bin/env python3
"""Diff two extraction_output JSON files (or two whole directories).

Match key: (question_timestamp, question_asker). Reports added, dropped,
changed, identical. Used for prompt-regression validation: snapshot baseline,
re-run extraction, diff to confirm no genuine Qs lost and no over-extraction.

Usage:
    scripts/diff_extraction.py BASELINE CANDIDATE
    scripts/diff_extraction.py --dir BASELINE_DIR CANDIDATE_DIR
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def _key(q: dict) -> tuple[str, str]:
    return (q.get("question_timestamp", ""), q.get("question_asker", ""))


def _summary(q: dict) -> str:
    txt = (q.get("question_text") or "").strip().replace("\n", " ")
    return txt[:120] + ("…" if len(txt) > 120 else "")


def diff_files(baseline: list[dict], candidate: list[dict]) -> dict:
    base_by_key = {_key(q): q for q in baseline}
    cand_by_key = {_key(q): q for q in candidate}
    base_keys = set(base_by_key)
    cand_keys = set(cand_by_key)

    dropped = sorted(base_keys - cand_keys)
    added = sorted(cand_keys - base_keys)
    common = base_keys & cand_keys

    changed = []
    identical = 0
    fields_to_compare = (
        "question_text", "answer_text", "answer_solver", "answer_confirmed",
        "is_session_question", "session_quizmaster", "session_theme",
        "session_quiz_type", "topics", "extraction_confidence",
    )
    for k in common:
        b, c = base_by_key[k], cand_by_key[k]
        deltas = {f: (b.get(f), c.get(f)) for f in fields_to_compare if b.get(f) != c.get(f)}
        b_disc = len(b.get("discussion") or [])
        c_disc = len(c.get("discussion") or [])
        if b_disc != c_disc:
            deltas["discussion_count"] = (b_disc, c_disc)
        if deltas:
            changed.append({"key": k, "deltas": deltas, "summary": _summary(b)})
        else:
            identical += 1

    return {
        "summary": {
            "baseline_count": len(baseline),
            "candidate_count": len(candidate),
            "identical": identical,
            "changed": len(changed),
            "dropped": len(dropped),
            "added": len(added),
        },
        "dropped": [{"key": list(k), "summary": _summary(base_by_key[k])} for k in dropped],
        "added":   [{"key": list(k), "summary": _summary(cand_by_key[k])} for k in added],
        "changed": changed,
    }


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def diff_dirs(base_dir: Path, cand_dir: Path) -> dict:
    out: dict[str, dict] = {}
    for f in sorted(base_dir.glob("*.json")):
        cand_f = cand_dir / f.name
        out[f.stem] = diff_files(_load(f), _load(cand_f))
    for f in sorted(cand_dir.glob("*.json")):
        if f.stem not in out:
            out[f.stem] = diff_files([], _load(f))
    return out


def render_text(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"Baseline: {s['baseline_count']} Qs   Candidate: {s['candidate_count']} Qs",
        f"  identical:  {s['identical']}",
        f"  changed:    {s['changed']}",
        f"  dropped:    {s['dropped']}  (in baseline, missing in candidate)",
        f"  added:      {s['added']}    (new in candidate)",
        "",
    ]
    if report["dropped"]:
        lines.append("=== DROPPED (potential REGRESSION — verify each is genuinely not a Q) ===")
        for d in report["dropped"]:
            lines.append(f"  [{d['key'][0]}] {d['key'][1]}")
            lines.append(f"    {d['summary']}")
        lines.append("")
    if report["added"]:
        lines.append("=== ADDED (verify each is a genuine trivia Q, not over-extraction) ===")
        for a in report["added"]:
            lines.append(f"  [{a['key'][0]}] {a['key'][1]}")
            lines.append(f"    {a['summary']}")
        lines.append("")
    if report["changed"]:
        lines.append("=== CHANGED (improvement or regression?) ===")
        for c in report["changed"]:
            lines.append(f"  [{c['key'][0]}] {c['key'][1]}")
            lines.append(f"    {c['summary']}")
            for field, (b, n) in c["deltas"].items():
                lines.append(f"    {field}: {b!r} → {n!r}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    ap.add_argument("--dir", action="store_true", help="Both args are directories of JSON files")
    ap.add_argument("--json", help="Write report JSON to this path")
    args = ap.parse_args()

    base = Path(args.baseline)
    cand = Path(args.candidate)

    if args.dir:
        report = diff_dirs(base, cand)
        # Aggregate text rendering
        agg = {"summary": {"identical": 0, "changed": 0, "dropped": 0, "added": 0,
                           "baseline_count": 0, "candidate_count": 0}}
        for date, r in report.items():
            for k in agg["summary"]:
                agg["summary"][k] += r["summary"][k]
        print(f"Per-date:")
        for date, r in sorted(report.items()):
            s = r["summary"]
            print(f"  {date}: base={s['baseline_count']} cand={s['candidate_count']} "
                  f"id={s['identical']} chg={s['changed']} dropped={s['dropped']} added={s['added']}")
        print()
        print("Aggregate:")
        print(render_text(agg))
        if args.json:
            Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        report = diff_files(_load(base), _load(cand))
        print(render_text(report))
        if args.json:
            Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Non-zero exit if regressions detected
    if not args.dir:
        return 1 if report["summary"]["dropped"] > 0 else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
