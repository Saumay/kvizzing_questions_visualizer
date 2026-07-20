#!/usr/bin/env python3
"""
Upload quiz_decks/ files referenced in v2/visualizer/static/data/decks.json to
Cloudflare R2, then patch the manifest's `url` fields in place.

Run scripts/build_decks_manifest.py first (or after adding new decks).

Required env vars:
    R2_ACCOUNT_ID         Cloudflare account ID
    R2_ACCESS_KEY_ID      R2 API token access key
    R2_SECRET_ACCESS_KEY  R2 API token secret key
    R2_BUCKET             Bucket name (e.g. "kvizzing-media")
    R2_PUBLIC_URL         Public base URL (e.g. "https://pub-xxx.r2.dev")

Usage:
    python3 scripts/upload_decks_to_r2.py            # upload + patch manifest
    python3 scripts/upload_decks_to_r2.py --dry-run   # list what would upload
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
from pathlib import Path
from urllib.parse import quote

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("upload_decks")

REPO_ROOT = Path(__file__).resolve().parent.parent
DECKS_DIR = REPO_ROOT / "quiz_decks"
MANIFEST_PATH = REPO_ROOT / "v2" / "visualizer" / "static" / "data" / "decks.json"

_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".mp4": "video/mp4",
    ".vtt": "text/vtt",
}


def _content_type(rel_path: str) -> str:
    ext = Path(rel_path).suffix.lower()
    return _CONTENT_TYPES.get(ext) or mimetypes.guess_type(rel_path)[0] or "application/octet-stream"


def _make_client():
    import boto3

    account_id = os.environ.get("R2_ACCOUNT_ID")
    access_key_id = os.environ.get("R2_ACCESS_KEY_ID")
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    missing = [k for k, v in [
        ("R2_ACCOUNT_ID", account_id),
        ("R2_ACCESS_KEY_ID", access_key_id),
        ("R2_SECRET_ACCESS_KEY", secret_access_key),
    ] if not v]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )


def _iter_files(manifest: dict):
    for s in manifest["series"]:
        for r in s["rounds"]:
            for f in r["files"]:
                yield f
    for d in manifest["standalone"]:
        for f in d["files"]:
            yield f


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text())
    to_upload = [f for f in _iter_files(manifest) if f["url"] is None]

    if not to_upload:
        log.info("Nothing to upload — all files already have URLs.")
        return

    log.info("%d file(s) pending upload (%.1f MB)", len(to_upload),
              sum(f["size_bytes"] for f in to_upload) / 1024 ** 2)

    if args.dry_run:
        for f in to_upload:
            log.info("  [dry-run] %s -> %s", f["rel_path"], f["r2_key"])
        return

    bucket = os.environ.get("R2_BUCKET")
    public_base = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")
    if not bucket or not public_base:
        raise RuntimeError("Set R2_BUCKET and R2_PUBLIC_URL env vars.")

    client = _make_client()

    uploaded = 0
    for f in to_upload:
        local = DECKS_DIR / f["rel_path"]
        if not local.exists():
            log.warning("  Missing locally, skipping: %s", f["rel_path"])
            continue
        log.info("  Uploading %s (%.1f MB)…", f["rel_path"], f["size_bytes"] / 1024 ** 2)
        client.upload_file(
            str(local), bucket, f["r2_key"],
            ExtraArgs={"ContentType": _content_type(f["rel_path"])},
        )
        f["url"] = f"{public_base}/{quote(f['r2_key'])}"
        uploaded += 1

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    log.info("Uploaded %d/%d file(s). Manifest updated: %s",
              uploaded, len(to_upload), MANIFEST_PATH.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
