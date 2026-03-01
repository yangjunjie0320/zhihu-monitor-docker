"""Logging configuration."""

import logging
import logging.handlers
import os
from pathlib import Path


def setup_logging(log_file: Path) -> None:
    """Setup logging with file rotation and console output.

    Args:
        log_file: Path to log file
    """
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Create formatter
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # File handler with rotation (keep 15 days, rotate daily)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_file),
        when='midnight',
        interval=1,
        backupCount=15,  # Keep 15 days of logs
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Prevent duplicate logs from requests library
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
