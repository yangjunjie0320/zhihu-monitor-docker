"""State persistence management."""

import json
import logging
from pathlib import Path
from typing import Set

from .models import State
from .time_utils import TimeUtils

logger = logging.getLogger(__name__)


class StateManager:
    """Manages monitor state persistence."""

    def __init__(self, state_file: Path, max_seen_ids: int = 1000):
        """Initialize state manager.

        Args:
            state_file: Path to state file
            max_seen_ids: Maximum number of seen IDs to keep
        """
        self.state_file = state_file
        self.max_seen_ids = max_seen_ids

    def load(self) -> State:
        """Load state from file, return empty state if file doesn't exist."""
        if not self.state_file.exists():
            logger.info("State file not found, initializing empty state")
            return State()

        try:
            content = self.state_file.read_text(encoding="utf-8")
            data = json.loads(content)

            if not isinstance(data, dict):
                logger.warning("Invalid state file format, initializing empty state")
                return State()

            # Parse datetime strings
            if data.get("last_check"):
                data["last_check"] = TimeUtils.parse_datetime(data["last_check"])
            if data.get("last_notification_time"):
                data["last_notification_time"] = TimeUtils.parse_datetime(data["last_notification_time"])
            if data.get("last_cookie_reminder_time"):
                data["last_cookie_reminder_time"] = TimeUtils.parse_datetime(data["last_cookie_reminder_time"])
            if data.get("last_error_report_time"):
                data["last_error_report_time"] = TimeUtils.parse_datetime(data["last_error_report_time"])

            return State(**data)

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to load state file: {e}, initializing empty state")
            return State()

    def save(self, state: State) -> None:
        """Save state to file with error handling."""
        try:
            # Update last check time
            state.last_check = TimeUtils.now_utc()

            # Convert to dict with ISO format datetimes
            data = {
                "seen_ids": state.seen_ids,
                "last_check": state.last_check.isoformat() if state.last_check else None,
                "last_notification_time": state.last_notification_time.isoformat() if state.last_notification_time else None,
                "last_cookie_reminder_time": state.last_cookie_reminder_time.isoformat() if state.last_cookie_reminder_time else None,
                "last_error_report_time": state.last_error_report_time.isoformat() if state.last_error_report_time else None,
            }

            # Ensure directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            # Write to file
            content = json.dumps(data, ensure_ascii=False, indent=2)
            self.state_file.write_text(content, encoding="utf-8")

            logger.debug(f"State saved. last_check: {state.last_check}")

        except Exception as e:
            logger.error(f"Failed to save state file: {e}")

    def add_seen_ids(self, state: State, seen_ids: Set[str]) -> None:
        """Add seen IDs to state, keeping only the latest max_seen_ids.

        Args:
            state: State object to update
            seen_ids: Set of seen IDs to add
        """
        # Merge with existing IDs and keep only the most recent ones
        state.seen_ids = list(seen_ids)[-self.max_seen_ids:]

    def is_seen(self, state: State, item_id: str) -> bool:
        """Check if item ID has been seen.

        Args:
            state: State object
            item_id: Item ID to check

        Returns:
            True if item has been seen
        """
        return item_id in state.seen_ids

    def update_notification_time(self, state: State) -> None:
        """Update last notification time to now."""
        state.last_notification_time = TimeUtils.now_utc()
        logger.debug(f"Updated last_notification_time: {state.last_notification_time}")

    def update_cookie_reminder_time(self, state: State) -> None:
        """Update last cookie reminder time to now."""
        state.last_cookie_reminder_time = TimeUtils.now_utc()

    def update_error_report_time(self, state: State) -> None:
        """Update last error report time to now."""
        state.last_error_report_time = TimeUtils.now_utc()

    def clear_error_report_time(self, state: State) -> None:
        """Clear error report time (when errors are resolved)."""
        if state.last_error_report_time:
            logger.info("All errors resolved, clearing error report time")
            state.last_error_report_time = None
