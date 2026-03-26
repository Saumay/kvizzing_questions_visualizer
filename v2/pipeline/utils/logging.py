"""Logging setup — call setup() once at startup."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup(log_dir: Path) -> logging.Logger:
    """
    Configure the 'kvizzing' logger to write to both stdout and pipeline.log.
    Safe to call multiple times (handlers are only added once).
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pipeline.log"

    ts_fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    plain_fmt = logging.Formatter("%(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(ts_fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(plain_fmt)

    logger = logging.getLogger("kvizzing")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger
