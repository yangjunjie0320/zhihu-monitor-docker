"""Core monitoring logic."""

import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

from .constants import ContentType
from .models import Config, Item, State
from .rss_client import RSSClient
from .state_manager import StateManager
from .time_utils import TimeUtils
from .webhook_client import WebhookClient

logger = logging.getLogger(__name__)


class Monitor:
    """Monitor Zhihu user updates and send notifications via webhook."""

    def __init__(self, config: Config):
        """Initialize monitor with configuration.

        Args:
            config: Monitor configuration
        """
        self.config = config
        self.state_manager = StateManager(config.state_file, config.max_seen_ids)
        self.rss_client = RSSClient(config)
        self.webhook_client = WebhookClient(config)

    def _get_item_id(self, item: Dict) -> Optional[str]:
        """Generate item ID from item data.

        Args:
            item: Item data dictionary

        Returns:
            Item ID or None
        """
        item_id = item.get("id")
        if item_id:
            return item_id

        url = item.get("url", "")
        if url:
            return hashlib.md5(url.encode()).hexdigest()

        return None

    def _process_items(
        self,
        data: Dict,
        content_type: ContentType,
        state: State,
        seen: Set[str]
    ) -> List[Item]:
        """Process RSS items and return new items.

        Args:
            data: RSS data dictionary
            content_type: Type of content
            state: Current state
            seen: Set of seen IDs (will be updated)

        Returns:
            List of new items
        """
        items = data.get("items", [])
        if not isinstance(items, list):
            logger.warning(f"Invalid items format for {content_type.display_name}")
            return []

        new_items = []
        for item in items:
            if not isinstance(item, dict):
                logger.warning(f"Invalid item format in {content_type.display_name}, skipping")
                continue

            item_id = self._get_item_id(item)
            if not item_id:
                logger.warning("Item missing both id and url, skipping")
                continue

            if item_id not in seen:
                title = item.get("title", "")[:50]
                logger.info(f"New {content_type.display_name}: {title}")

                new_item = Item(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content_html=item.get("content_html", ""),
                    content_text=item.get("content_text", ""),
                    summary=item.get("summary", "")
                )
                new_items.append(new_item)
                seen.add(item_id)

        return new_items

    def _should_send_reminder(self, state: State) -> bool:
        """Check if reminder should be sent.

        Args:
            state: Current state

        Returns:
            True if reminder should be sent
        """
        last_notification = state.last_notification_time or state.last_check
        if not last_notification:
            logger.debug("No last notification time found, skipping reminder check")
            return False

        hours_passed = TimeUtils.hours_since(last_notification)
        logger.debug(f"Hours since last notification: {hours_passed:.2f}")

        return hours_passed >= self.config.reminder_hours

    def _should_send_error_report(self, state: State) -> bool:
        """Check if error report should be sent.

        Args:
            state: Current state

        Returns:
            True if error report should be sent
        """
        if not state.last_error_report_time:
            return True

        hours_passed = TimeUtils.hours_since(state.last_error_report_time)
        logger.debug(f"Hours since last error report: {hours_passed:.2f}")

        return hours_passed >= self.config.error_report_interval_hours

    def _get_cookie_file_mtime(self) -> Optional[datetime]:
        """Get modification time of cookie file.

        Returns:
            Modification time or None if file doesn't exist
        """
        if self.config.cookie_file.exists():
            return datetime.fromtimestamp(
                self.config.cookie_file.stat().st_mtime,
                tz=TimeUtils.now_utc().tzinfo
            )
        return None

    def _check_cookie_expiry(self, state: State) -> None:
        """Check cookie file expiry and send reminder if needed.

        Args:
            state: Current state
        """
        cookie_mtime = self._get_cookie_file_mtime()
        if not cookie_mtime:
            logger.warning(f"Cookie file not found: {self.config.cookie_file}")
            return

        expiry_date = cookie_mtime + timedelta(days=self.config.cookie_expiry_days)
        days_until_expiry = (expiry_date - TimeUtils.now_utc()).days

        should_send_reminder = False

        if not state.last_cookie_reminder_time:
            should_send_reminder = True
        else:
            days_since_last_reminder = (
                TimeUtils.now_utc() - state.last_cookie_reminder_time
            ).days
            if days_since_last_reminder >= self.config.cookie_reminder_interval_days:
                should_send_reminder = True

        if should_send_reminder and days_until_expiry > 0:
            if self.webhook_client.send_cookie_expiry_reminder(
                cookie_mtime, expiry_date, days_until_expiry
            ):
                self.state_manager.update_cookie_reminder_time(state)
                logger.info(f"Cookie expiry reminder sent: {days_until_expiry} days until expiry")

        elif days_until_expiry <= 0:
            logger.warning(
                f"Cookie file has expired! Last modified: {cookie_mtime}, "
                f"Expiry: {expiry_date}"
            )

    def check_updates(self) -> int:
        """Check for updates and return count of new items found.

        Returns:
            Number of new items found
        """
        logger.info(f"Checking updates for {self.config.user_name}...")
        if self.config.debug_mode:
            logger.info("DEBUG MODE ENABLED - will send notification even if no new items found")

        state = self.state_manager.load()
        logger.debug(
            f"Loaded state: last_notification_time={state.last_notification_time}, "
            f"last_check={state.last_check}"
        )

        seen: Set[str] = set(state.seen_ids)
        new_items_by_type: Dict[ContentType, List[Item]] = {}
        errors: List[str] = []

        fetch_results = self.rss_client.fetch_all()
        for content_type, (data, error) in fetch_results.items():
            if error:
                errors.append(f"{content_type.display_name}: {error}")
            if not data:
                continue

            new_items = self._process_items(data, content_type, state, seen)
            if new_items:
                new_items_by_type[content_type] = new_items

        has_errors = len(errors) > 0
        if has_errors:
            logger.warning(f"Encountered {len(errors)} error(s) during check")
            if self._should_send_error_report(state):
                if self.webhook_client.send_error_report(errors):
                    self.state_manager.update_error_report_time(state)
                    logger.info("Error report sent")
            else:
                hours_until_next = (
                    self.config.error_report_interval_hours -
                    TimeUtils.hours_since(state.last_error_report_time)
                )
                logger.info(
                    f"Errors detected but skipping report "
                    f"(next report in {hours_until_next:.1f}h)"
                )
        else:
            # No errors, clear error report time if it exists
            self.state_manager.clear_error_report_time(state)

        new_count = sum(len(items) for items in new_items_by_type.values())
        logger.debug(f"Found {new_count} new items")

        notification_sent = False
        if has_errors:
            logger.info("Errors detected, skipping normal notifications")
        else:
            for content_type, items in new_items_by_type.items():
                if items:
                    content_types = [content_type] * len(items)
                    if self.webhook_client.send_new_items(items, content_types):
                        notification_sent = True

            if notification_sent:
                self.state_manager.update_notification_time(state)

            # In debug mode, send notification even if no new items
            if self.config.debug_mode and new_count == 0:
                logger.info("Debug mode: sending notification even though no new items found")
                if self.webhook_client.send_debug_notification():
                    self.state_manager.update_notification_time(state)

            elif new_count == 0:
                # Send reminder if no new content (normal mode)
                logger.debug("No new items found, checking reminder condition")
                if self._should_send_reminder(state):
                    logger.info(f"Reminder condition met: >= {self.config.reminder_hours} hours")
                    if self.webhook_client.send_reminder():
                        self.state_manager.update_notification_time(state)
                        logger.info("Reminder notification sent")
            else:
                logger.debug(f"New items found ({new_count}), skipping reminder check")

        self._check_cookie_expiry(state)

        self.state_manager.add_seen_ids(state, seen)
        self.state_manager.save(state)

        logger.info(f"Completed, found {new_count} new items")
        return new_count
