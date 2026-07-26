"""
Precompute semantic-search embeddings for every question, so the visualizer's
"check for duplicates" tool can compare a newly-drafted question against the
whole question bank entirely client-side (no backend — see the int8 note
below for why this stays small enough to ship as a static asset).

Model: sentence-transformers/all-MiniLM-L6-v2 (384-dim), embeddings
L2-normalized so cosine similarity reduces to a plain dot product. The
browser side (transformers.js, running the ONNX port of the same model)
must use the same normalization for query embeddings to be comparable.

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
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

V2_DIR = Path(__file__).parent.parent.parent
QUESTIONS_JSON = V2_DIR / "visualizer" / "static" / "data" / "questions.json"
OUT_BIN = V2_DIR / "visualizer" / "static" / "data" / "question_embeddings.bin"
OUT_META = V2_DIR / "visualizer" / "static" / "data" / "question_embeddings_meta.json"

MODEL_NAME = "all-MiniLM-L6-v2"
QUANT_SCALE = 127  # embeddings are unit-normalized, so components are in [-1, 1]


def main() -> None:
    from sentence_transformers import SentenceTransformer

    questions = json.loads(QUESTIONS_JSON.read_text())
    ids = [q["id"] for q in questions]
    texts = [q["question"]["text"] for q in questions]
    print(f"Encoding {len(texts)} questions with {MODEL_NAME}...")

    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(
        texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True
    )

    quantized = np.clip(np.round(embeddings * QUANT_SCALE), -127, 127).astype(np.int8)

    OUT_BIN.write_bytes(quantized.tobytes())
    OUT_META.write_text(json.dumps({
        "model": MODEL_NAME,
        "dim": embeddings.shape[1],
        "scale": QUANT_SCALE,
        "count": len(ids),
        "ids": ids,
    }, indent=2) + "\n")

    print(f"Wrote {OUT_BIN.relative_to(V2_DIR)} ({OUT_BIN.stat().st_size / 1024:.0f} KB)")
    print(f"Wrote {OUT_META.relative_to(V2_DIR)}")


if __name__ == "__main__":
    main()
