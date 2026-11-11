"""
Dump a PPTX deck's slide text and embedded images for manual/agent-driven
Q&A extraction, without needing LibreOffice or Keynote to render it to PDF.

python-pptx reads the PPTX's slide text frames directly (usually enough on
its own for text-based quiz decks) and extracts embedded images to disk for
decks that use picture-only clues (rebus rounds, "identify this photo", etc).
Requires `pip install python-pptx` (a throwaway .venv works fine, see
v2/pipeline/.venv in .gitignore).

Usage:
    python3 pptx_dump.py <deck.pptx> <output_image_dir>

Prints one block per slide (image count + any text found), and saves each
embedded image as <output_image_dir>/slide<N>_img<M>.<ext> for slides that
need a closer look.
"""

import sys
from pathlib import Path
from pptx import Presentation

PICTURE_SHAPE_TYPE = 13
GROUP_SHAPE_TYPE = 6


def _walk_shapes(shapes):
    """Yield every shape, recursing into GROUP shapes — group members (e.g. a
    picture nested inside a Google-Slides-exported group) aren't visited by a
    flat `for shape in slide.shapes` loop otherwise, so a slide can silently
    report 0 images despite holding picture-only clues inside a group."""
    for shape in shapes:
        yield shape
        if shape.shape_type == GROUP_SHAPE_TYPE:
            yield from _walk_shapes(shape.shapes)


def dump(pptx_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    prs = Presentation(str(pptx_path))
    print(f"{len(prs.slides)} slides in {pptx_path.name}")

    for i, slide in enumerate(prs.slides, start=1):
        texts = []
        img_count = 0
        for shape in _walk_shapes(slide.shapes):
            if shape.has_text_frame and shape.text_frame.text.strip():
                texts.append(shape.text_frame.text.strip())
            if shape.shape_type == PICTURE_SHAPE_TYPE:
                img_count += 1
                img = shape.image
                img_path = out_dir / f"slide{i:02d}_img{img_count}.{img.ext}"
                img_path.write_bytes(img.blob)
        print(f"--- slide {i} ({img_count} image(s)) ---")
        for t in texts:
            print(t)
        print()


if __name__ == "__main__":
    dump(Path(sys.argv[1]), Path(sys.argv[2]))
