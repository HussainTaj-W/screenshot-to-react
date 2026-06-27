"""Centralized logging configuration for the pipeline.

Use a single ``pipeline`` logger so the CLI can configure verbosity once and
every stage/agent/graph node logs progress through it.
"""

from __future__ import annotations

import logging
import sys

LOGGER_NAME = "pipeline"


def get_logger(suffix: str | None = None) -> logging.Logger:
    """Return the pipeline logger (optionally a named child)."""
    name = LOGGER_NAME if not suffix else f"{LOGGER_NAME}.{suffix}"
    return logging.getLogger(name)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the ``pipeline`` logger to stream to stdout.

    Idempotent: calling more than once won't add duplicate handlers.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    if any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        for h in logger.handlers:
            h.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
