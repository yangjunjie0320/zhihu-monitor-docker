"""Data models for Zhihu monitor."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class Item:
    """Zhihu content item."""

    title: str
    url: str
    content_html: str = ""
    content_text: str = ""
    summary: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "url": self.url,
            "content_html": self.content_html,
            "content_text": self.content_text,
            "summary": self.summary
        }


@dataclass
class State:
    """Monitor state."""

    seen_ids: List[str] = field(default_factory=list)
    last_check: Optional[datetime] = None
    last_notification_time: Optional[datetime] = None
    last_cookie_reminder_time: Optional[datetime] = None
    last_error_report_time: Optional[datetime] = None


@dataclass
class Config:
    """Configuration for Zhihu monitor."""

    # Required settings
    webhook_url: str

    # User settings
    user_id: str = "shui-qian-xiao-xi"
    user_name: str = "马前卒official"

    # Service settings
    rsshub_base: str = "http://rsshub:1200"

    # File paths
    state_file: Path = Path("/data/state.json")
    cookie_file: Path = Path("/data/cookies.txt")
    log_file: Path = Path("/data/monitor.log")

    # Feature flags
    debug_mode: bool = False

    # Time intervals
    cookie_expiry_days: int = 15
    cookie_reminder_interval_days: int = 5
    reminder_hours: int = 24
    error_report_interval_hours: int = 24

    # Limits
    max_seen_ids: int = 1000
