"""
Scan v2/visualizer/static/images/sessions/ for Stable Horde "CENSORED"
placeholder cards (see detect_censored_image.py) — these slip in whenever
generate_session_images.py is run against new sessions, since the free/anon
queue's own NSFW filter false-positives occasionally.

Usage:
    python3 v2/pipeline/utils/audit_session_images.py            # report only
    python3 v2/pipeline/utils/audit_session_images.py --delete   # report + delete
                                                                  #   (rerun the
                                                                  #   generator
                                                                  #   afterward to
                                                                  #   backfill)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from detect_censored_image import is_censored_placeholder

V2_DIR = Path(__file__).parent.parent.parent
SESSIONS_IMAGES_DIR = V2_DIR / "visualizer" / "static" / "images" / "sessions"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delete", action="store_true", help="Delete flagged files")
    args = parser.parse_args()

    files = sorted(SESSIONS_IMAGES_DIR.glob("*.jpg"))
    flagged = [f for f in files if is_censored_placeholder(f)]

    print(f"Scanned {len(files)} images.")
    if not flagged:
        print("No CENSORED placeholders found.")
        return

    print(f"Flagged {len(flagged)}:")
    for f in flagged:
        print(f"  {f.relative_to(V2_DIR)}")

    if args.delete:
        for f in flagged:
            f.unlink()
        print(f"\nDeleted {len(flagged)} file(s). Rerun generate_session_images.py to backfill.")
    else:
        print("\nRun with --delete to remove them, then rerun generate_session_images.py.")


if __name__ == "__main__":
    main()
