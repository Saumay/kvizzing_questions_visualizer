"""
Detect connect quizzes among existing sessions using LLM classification.

Sends each session's questions to the LLM and asks if it's a connect quiz
(hidden theme connecting all questions) vs a regular themed quiz.

Usage:
    GEMINI_API_KEY=xxx python3 utils/detect_connect_quizzes.py [--apply]
"""

from __future__ import annotations

import json
import logging  # must import before sys.path modification
import re
import sys
import time
from pathlib import Path

# Insert pipeline dir but AFTER utils/ so stdlib logging isn't shadowed
_pipeline_dir = str(Path(__file__).parent.parent)
if _pipeline_dir not in sys.path:
    sys.path.append(_pipeline_dir)
from clients.llm import get_client
from utils.config import load_config


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write to session_overrides.json")
    args = parser.parse_args()

    v2_dir = Path(__file__).parent.parent.parent
    sessions = json.loads((v2_dir / "visualizer/static/data/sessions.json").read_text())
    questions = json.loads((v2_dir / "visualizer/static/data/questions.json").read_text())
    config = load_config(Path(__file__).parent.parent / "config")
    rate_limit_sleep = config.get("stage2", {}).get("llm_rate_limit_sleep_seconds", 13)

    client = get_client()
    if not client:
        print("No LLM client. Set GEMINI_API_KEY.")
        sys.exit(1)

    # Use the client's default model (e.g. gemini-2.5-pro for GeminiClient)
    model = getattr(client, '_model', None) or "gemini-2.5-pro"

    candidates = [s for s in sessions if s.get("quiz_type") != "connect" and s["question_count"] >= 5]
    print(f"Checking {len(candidates)} sessions for connect quiz pattern...\n")

    connect_found = []
    for s in candidates:
        session_qs = [
            q for q in questions
            if q.get("session") and isinstance(q["session"], dict) and q["session"].get("id") == s["id"]
        ]

        q_summaries = []
        for q in session_qs[:15]:
            qt = (q.get("question", {}).get("text") or "")[:150]
            ans = (q.get("answer", {}).get("text") or "")[:80]
            q_summaries.append(f"Q: {qt}\nA: {ans}")

        theme = s.get("theme") or f"{s['quizmaster']}'s Quiz"
        prompt = (
            f"Session: {theme}\nQuizmaster: {s['quizmaster']}\n"
            f"{len(session_qs)} questions:\n\n"
            + "\n---\n".join(q_summaries)
            + "\n\nIs this a CONNECT QUIZ — where all questions share a hidden connecting theme "
            "that participants try to guess? A connect quiz has seemingly unrelated questions "
            "whose answers all connect to one hidden theme revealed at the end.\n"
            "This is NOT a themed quiz where the topic is announced upfront.\n\n"
            'Reply ONLY with JSON: {"is_connect": true/false, "reason": "brief explanation"}'
        )

        try:
            resp = client.messages.create(
                model=model,
                max_tokens=8192,
                system="You classify quiz sessions. Answer only with JSON.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (resp.content[0].text or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw).strip()
            if raw:
                result = json.loads(raw)
                if result.get("is_connect"):
                    connect_found.append(s["id"])
                    print(f"  CONNECT: {s['id']} — {result.get('reason', '')}")
                else:
                    print(f"  regular: {s['id']}")
        except Exception as e:
            print(f"  error:   {s['id']}: {e}")

        time.sleep(rate_limit_sleep)

    print(f"\n{len(connect_found)} connect quiz(zes) found.")

    if connect_found and args.apply:
        overrides_path = Path(__file__).parent.parent / "config/session_overrides.json"
        overrides = json.loads(overrides_path.read_text())
        for sid in connect_found:
            if sid not in overrides:
                overrides[sid] = {}
            overrides[sid]["quiz_type"] = "connect"
        overrides_path.write_text(json.dumps(overrides, indent=2, ensure_ascii=False))
        print(f"Updated session_overrides.json with {len(connect_found)} connect quiz(zes).")
        print("Run 'python3 pipeline.py export' to apply.")
    elif connect_found:
        print("Run with --apply to update session_overrides.json.")


if __name__ == "__main__":
    main()
