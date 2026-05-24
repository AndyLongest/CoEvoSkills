from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logger(name: str = "coevo", level: int = logging.INFO, log_file: Path | None = None) -> logging.Logger:
    """Create a structured logger with optional file output."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    # Also configure root logger so sub-modules (utils.agent.*, layers.*, etc.) are captured
    root = logging.getLogger()
    if not root.handlers:
        root_handler = logging.StreamHandler(sys.stderr)
        root_handler.setFormatter(fmt)
        root.addHandler(root_handler)
    root.setLevel(level)

    return logger
