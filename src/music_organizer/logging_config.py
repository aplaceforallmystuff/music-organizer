"""Logging configuration for music organizer."""

import logging
import sys
from pathlib import Path

# Create logger
logger = logging.getLogger("music_organizer")


def setup_logging(verbose: bool = False, log_file: Path | None = None):
    """Configure logging for the application.

    Args:
        verbose: If True, log DEBUG level to console
        log_file: If provided, also log to this file
    """
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console_format = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler (if requested)
    if log_file:
        file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
        logger.info(f"Logging to {log_file}")

    return logger
