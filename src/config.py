"""Configuration management."""

import os
from pathlib import Path

from .models import Config


def load_config_from_env() -> Config:
    """Load configuration from environment variables."""
    return Config(
        # Required
        webhook_url=os.getenv("WEBHOOK_URL", ""),

        # User settings
        user_id=os.getenv("ZHIHU_USER_ID", "shui-qian-xiao-xi"),
        user_name=os.getenv("ZHIHU_USER_NAME", "马前卒official"),

        # Service settings
        rsshub_base=os.getenv("RSSHUB_BASE", "http://rsshub:1200"),

        # File paths
        state_file=Path(os.getenv("STATE_FILE", "/data/state.json")),
        cookie_file=Path(os.getenv("COOKIE_FILE", "/data/cookies.txt")),
        log_file=Path(os.getenv("LOG_FILE", "/data/monitor.log")),

        # Feature flags
        debug_mode=os.getenv("DEBUG_MODE", "").lower() in ("true", "1", "yes", "on"),

        # Time intervals
        cookie_expiry_days=int(os.getenv("COOKIE_EXPIRY_DAYS", "15")),
        cookie_reminder_interval_days=int(os.getenv("COOKIE_REMINDER_INTERVAL_DAYS", "5")),
        reminder_hours=int(os.getenv("REMINDER_HOURS", "24")),
        error_report_interval_hours=int(os.getenv("ERROR_REPORT_INTERVAL_HOURS", "24")),

        # Limits
        max_seen_ids=int(os.getenv("MAX_SEEN_IDS", "1000")),
    )
