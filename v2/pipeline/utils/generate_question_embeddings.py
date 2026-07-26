"""
Precompute semantic-search embeddings for every question, so the visualizer's
"check for duplicates" tool can compare a newly-drafted question against the
whole question bank entirely client-side (no backend — see the int8 note
below for why this stays small enough to ship as a static asset).

Model: sentence-transformers/all-MiniLM-L6-v2 (384-dim), embeddings
L2-normalized so cosine similarity reduces to a plain dot product. The
browser side (transformers.js, running the ONNX port of the same model)
must use the same normalization for query embeddings to be comparable.

Text used: question text + answer text, concatenated. Question-only was
tried first and dropped after empirical testing showed real failures: many
questions are terse (single word, code, or number, e.g. "OR Tambo Intl")
and only become meaningful with the answer attached, and connect/riddle
questions describe clues rather than the underlying topic, so a paraphrase
of the answer's topic doesn't match the clue text at all. Concatenating the
answer fixed both failure modes across a 5-case manual test.

Quantization: each embedding is L2-normalized, so every component is
guaranteed to lie in [-1, 1] — quantize with a fixed global scale of 127
(int8 range) rather than a per-vector scale. This keeps the output format
simple (raw int8 bytes, no per-vector scale factor to store) at the cost of
a small, uniform precision loss that's negligible for near-duplicate
detection. At 3.1k questions this is a 9.5MB -> ~1.2MB win; the real payoff
is at the 50k+ questions this is expected to grow to, where unquantized
float32 would be a ~73MB fetch vs ~19MB quantized.

Output:
  v2/visualizer/static/data/question_embeddings.bin   — raw int8, dim bytes per question, same order as `ids`
  v2/visualizer/static/data/question_embeddings_meta.json — {model, dim, scale, ids}

Install:
  pip install sentence-transformers

Run from anywhere:
  python3 v2/pipeline/utils/generate_question_embeddings.py

Also called automatically from pipeline.py after every export (best-effort —
see pipeline.py's _maybe_regenerate_embeddings), so the duplicate-check
corpus stays in sync with questions.json without a separate manual step.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

V2_DIR = Path(__file__).parent.parent.parent
DEFAULT_OUTPUT_DIR = V2_DIR / "visualizer" / "static" / "data"

MODEL_NAME = "all-MiniLM-L6-v2"
QUANT_SCALE = 127  # embeddings are unit-normalized, so components are in [-1, 1]


def main(output_dir: Path | None = None) -> None:
    from sentence_transformers import SentenceTransformer

    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    questions_json = output_dir / "questions.json"
    out_bin = output_dir / "question_embeddings.bin"
    out_meta = output_dir / "question_embeddings_meta.json"

    questions = json.loads(questions_json.read_text())
    ids = [q["id"] for q in questions]
    texts = [
        q["question"]["text"] + " " + (q["answer"]["text"] or "")
        for q in questions
    ]
    print(f"Encoding {len(texts)} questions with {MODEL_NAME}...")

    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(
        texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True
    )

    quantized = np.clip(np.round(embeddings * QUANT_SCALE), -127, 127).astype(np.int8)

    out_bin.write_bytes(quantized.tobytes())
    out_meta.write_text(json.dumps({
        "model": MODEL_NAME,
        "dim": embeddings.shape[1],
        "scale": QUANT_SCALE,
        "count": len(ids),
        "ids": ids,
    }, indent=2) + "\n")

    print(f"Wrote {out_bin} ({out_bin.stat().st_size / 1024:.0f} KB)")
    print(f"Wrote {out_meta}")


if __name__ == "__main__":
    main()
