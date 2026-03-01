#!/usr/bin/env python3
"""
Zhihu user monitoring script - single run version
Scheduled by Ofelia
"""

import logging
import os

from src.config import load_config_from_env
from src.logging_config import setup_logging
from src.monitor import Monitor
from src.time_utils import TimeUtils

logger = logging.getLogger(__name__)


def detect_trigger_source() -> str:
    """Detect how the script was triggered.

    Returns:
        String describing the trigger source
    """
    if os.getenv('OFELIA_JOB_NAME'):
        return "Ofelia scheduler"
    elif os.path.exists('/.dockerenv'):
        return "Ofelia scheduler (detected)"
    return "Manual execution"


def main() -> None:
    """Main entry point."""
    config = load_config_from_env()
    setup_logging(config.log_file)

    start_time = TimeUtils.now_utc()
    trigger_source = detect_trigger_source()

    logger.info("=" * 60)
    logger.info(f"Monitor script started at {start_time.isoformat()}")
    logger.info(f"Triggered by: {trigger_source}")
    logger.info(f"Monitoring user: {config.user_name} ({config.user_id})")
    logger.info("=" * 60)

    try:
        monitor = Monitor(config)
        new_count = monitor.check_updates()

        end_time = TimeUtils.now_utc()
        duration = (end_time - start_time).total_seconds()

        logger.info("=" * 60)
        logger.info(f"Monitor script completed in {duration:.2f} seconds")
        logger.info(f"Found {new_count} new items")
        logger.info(f"Finished at {end_time.isoformat()}")
        logger.info("=" * 60)

    except Exception as e:
        end_time = TimeUtils.now_utc()
        logger.error(f"Monitor script failed: {e}", exc_info=True)
        logger.error(f"Failed at {end_time.isoformat()}")
        raise


if __name__ == "__main__":
    main()
