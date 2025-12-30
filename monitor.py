#!/usr/bin/env python3
"""
Zhihu user monitoring script - single run version
Scheduled by Ofelia
"""

import os
import json
import hashlib
import re
import requests
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, LOG_LEVEL, logging.INFO)

format = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=log_level, format=format)
logger = logging.getLogger(__name__)

@dataclass
class Config:
    """Configuration for Zhihu monitor."""
    user_id: str
    user_name: str
    rsshub_base: str
    webhook_url: str
    state_file: Path
    debug_mode: bool

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        debug_mode = os.getenv("DEBUG_MODE", "").lower() in ("true", "1", "yes", "on")
        return cls(
            user_id=os.getenv("ZHIHU_USER_ID", "shui-qian-xiao-xi"),
            user_name=os.getenv("ZHIHU_USER_NAME", "马前卒official"),
            rsshub_base=os.getenv("RSSHUB_BASE", "http://rsshub:1200"),
            webhook_url=os.getenv("WEBHOOK_URL", ""),
            state_file=Path(os.getenv("STATE_FILE", "/data/state.json")),
            debug_mode=debug_mode,
        )

ROUTE_CN_TO_EN = {"回答": "answers", "想法": "pins"}
ROUTE_EN_TO_CN = {"answers": "回答", "pins": "想法"}

class Monitor:
    """Monitor Zhihu user updates and send notifications via webhook."""
    REMINDER_HOURS = 24
    MAX_SEEN_IDS = 1000

    def __init__(self, config: Config):
        """Initialize monitor with configuration."""
        self.config = config

    # ==================== Text Processing Methods ====================

    @staticmethod
    def has_image(html_content: str) -> bool:
        """Check if HTML content contains images."""
        if not html_content:
            return False
        return bool(re.search(r'<img[^>]*>', html_content, re.IGNORECASE))

    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean extracted text by removing HTML artifacts and normalizing whitespace."""
        if not text:
            return ""
        
        # Remove HTML tags and attributes
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+[a-z-]+="[^"]*"', '', text)
        
        # Decode HTML entities
        html_entities = {
            '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
            '&quot;': '"', '&#39;': "'"
        }
        for entity, char in html_entities.items():
            text = text.replace(entity, char)
        
        # Remove HTML-like patterns (quotes, brackets)
        text = re.sub(r'["\']\s*[><]', '', text)
        text = re.sub(r'[><]\s*["\']', '', text)
        text = re.sub(r'["\']\s*["\']', '', text)
        text = re.sub(r'^\s*[><]+\s*', '', text)
        text = re.sub(r'\s*[><]+\s*$', '', text)
        text = re.sub(r'\s*[><]\s*', ' ', text)
        
        # Clean up quotes and whitespace
        text = re.sub(r'^["\']+', '', text)
        text = re.sub(r'["\']+$', '', text)
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()

    @staticmethod
    def extract_text_from_html(html_content: str) -> str:
        """Extract plain text from HTML content."""
        if not html_content:
            return ""
        return Monitor._clean_text(html_content)

    @staticmethod
    def extract_first_n_chars(text: str, n: int = 20) -> str:
        """Extract first N Chinese characters from text."""
        if not text:
            return ""
        
        result = ""
        char_count = 0
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # Chinese character
                char_count += 1
            result += char
            if char_count >= n:
                break
        return result.strip()

    # ==================== Utility Methods ====================

    def _remove_user_prefix(self, text: str) -> str:
        """Remove user name prefix from text."""
        if not text:
            return text
        prefix = f"{self.config.user_name}："
        if text.startswith(prefix):
            return text[len(prefix):].strip()
        return text

    def _get_beijing_time_str(self) -> str:
        """Get current Beijing time as formatted string."""
        beijing_tz = timezone(timedelta(hours=8))
        beijing_time = datetime.now(beijing_tz)
        return beijing_time.strftime("%Y-%m-%d %H:%M")

    def _get_item_id(self, item: Dict) -> Optional[str]:
        """Generate item ID from item data."""
        item_id = item.get("id")
        if item_id:
            return item_id
        
        url = item.get("url", "")
        if url:
            return hashlib.md5(url.encode()).hexdigest()
        
        return None

    # ==================== State Management Methods ====================

    def load_state(self) -> Dict:
        """Load state from file, return empty state if file doesn't exist."""
        if not self.config.state_file.exists():
            return {"seen_ids": []}
        
        try:
            content = self.config.state_file.read_text(encoding="utf-8")
            state = json.loads(content)
            if not isinstance(state, dict):
                logger.warning("Invalid state file format, initializing empty state")
                return {"seen_ids": []}
            return state
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to load state file: {e}, initializing empty state")
            return {"seen_ids": []}

    def save_state(self, state: Dict) -> None:
        """Save state to file with error handling."""
        try:
            # Use UTC timezone for consistency
            state["last_check"] = datetime.now(timezone.utc).isoformat()
            self.config.state_file.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(state, ensure_ascii=False, indent=2)
            self.config.state_file.write_text(content, encoding="utf-8")
            logger.debug(f"State saved. last_check: {state['last_check']}")
        except Exception as e:
            logger.error(f"Failed to save state file: {e}")

    def _update_seen_ids(self, state: Dict, seen: Set[str]) -> None:
        """Update seen IDs in state, keeping only the latest MAX_SEEN_IDS."""
        state["seen_ids"] = list(seen)[-self.MAX_SEEN_IDS:]

    # ==================== RSS Fetching Methods ====================

    def fetch_rss(self, route: str) -> Optional[Dict]:
        """Fetch RSS data from RSSHub for given route."""
        url = f"{self.config.rsshub_base}/zhihu/people/{route}/{self.config.user_id}?format=json"
        try:
            resp = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                logger.warning(f"Invalid response format for route {route}")
                return None
            return data
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout for route {route}")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error for route {route}: {e}")
            return None
        except (requests.exceptions.RequestException, json.JSONDecodeError, Exception) as e:
            logger.error(f"Error fetching RSS for route {route}: {e}")
            return None

    # ==================== Webhook Methods ====================

    def _send_webhook_request(self, url: str, payload: Dict, timeout: int = 10) -> requests.Response:
        """Send webhook HTTP request."""
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response

    def _save_debug_info(self, url: str, payload: Dict, type_name: str, items: List[Dict], 
                         response: Optional[requests.Response] = None, error: Optional[str] = None) -> None:
        """Save debug information for webhook requests."""
        try:
            msg_type = payload.get("msg_type", "unknown")
            debug_record = {
                "timestamp": datetime.now().isoformat(),
                "url": url,
                "payload": payload,
                "status_code": response.status_code if response else None,
                "success": response is not None and response.status_code < 400,
                "error": error,
                "type": type_name,
                "items": items
            }
            
            debug_file = self.config.state_file.parent / "debug_history.json"
            history: Dict[str, Dict] = {}
            if debug_file.exists():
                try:
                    content = debug_file.read_text(encoding="utf-8")
                    history = json.loads(content)
                    if not isinstance(history, dict):
                        history = {}
                except Exception:
                    history = {}
            
            history[msg_type] = debug_record
            debug_file.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(history, ensure_ascii=False, indent=2)
            debug_file.write_text(content, encoding="utf-8")
            logger.debug(f"Debug info saved for msg_type: {msg_type}")
        except Exception as e:
            logger.error(f"Failed to save debug info: {e}")

    def _send_notification(self, url: str, payload: Dict, type_name: str, items: List[Dict]) -> bool:
        """Send notification webhook and save debug info."""
        response = None
        error = None
        
        try:
            response = self._send_webhook_request(url, payload)
            logger.info(f"Notification sent successfully: {len(items)} items")
            return True
        except requests.exceptions.Timeout as e:
            error = f"Timeout: {str(e)}"
            logger.error("Webhook request timeout")
            return False
        except requests.exceptions.HTTPError as e:
            error = f"HTTP error: {str(e)}"
            logger.error(f"Webhook HTTP error: {e}")
            return False
        except requests.exceptions.RequestException as e:
            error = f"Request error: {str(e)}"
            logger.error(f"Webhook request failed: {e}")
            return False
        except Exception as e:
            error = f"Unexpected error: {str(e)}"
            logger.error(f"Unexpected error sending webhook: {e}")
            return False
        finally:
            self._save_debug_info(url, payload, type_name, items, response, error)
        
        return False

    def _format_item_markdown(self, item: Dict, type_name: str) -> str:
        """Format a single item as Markdown line."""
        title = self._remove_user_prefix(item.get("title", ""))
        link = item.get("url", "")
        
        # Get content preview
        summary = item.get("summary", "")
        content_html = item.get("content_html", "") or item.get("content_text", "")
        
        if summary:
            content_preview = self.extract_first_n_chars(summary, 50)
            has_img = self.has_image(item.get("content_html", ""))
        else:
            content_text = self.extract_text_from_html(content_html)
            content_preview = self.extract_first_n_chars(content_text, 50)
            has_img = self.has_image(content_html)
        
        # Remove unwanted prefixes from content preview
        if content_preview:
            prefixes_to_remove = [
                f"New {type_name}: ",
                f"New {type_name}: {self.config.user_name}：",
                f"New {type_name}: {self.config.user_name}:",
                f"{self.config.user_name}：",
            ]
            for prefix in prefixes_to_remove:
                if content_preview.startswith(prefix):
                    content_preview = content_preview[len(prefix):].strip()
                    break
        
        # Format markdown line
        markdown_text = f"- [{title}]({link})"
        if type_name != "想法":
            if content_preview:
                markdown_text += f" {content_preview}"
            if has_img:
                markdown_text += " [图片]"
        
        return markdown_text

    def _format_message(self, items: List[Dict], type_names: List[str]) -> tuple[str, str]:
        """Format webhook message title and content."""
        type_name = type_names[0] if type_names else ""
        
        # Determine Chinese type name
        type_name_cn_map = {"回答": "新回答", "想法": "新想法"}
        type_name_cn = type_name_cn_map.get(type_name, type_name)
        
        time_str = self._get_beijing_time_str()
        message_title = f"{type_name_cn} {len(items)}条 获取时间：{time_str}"
        
        # Format items as markdown
        markdown_lines = [
            self._format_item_markdown(item, item_type)
            for item, item_type in zip(items, type_names)
        ]
        markdown_text = "\n".join(markdown_lines)
        
        # Remove any remaining user prefixes
        user_prefix = f"{self.config.user_name}："
        markdown_text = markdown_text.replace(user_prefix, "")
        
        return message_title, markdown_text

    def send_webhook(self, items: List[Dict], type_names: List[str]) -> bool:
        """Send webhook notification for multiple items in a single message."""
        url = self.config.webhook_url
        if not url or not items:
            if not url:
                logger.warning("WEBHOOK_URL not configured, skipping notification")
            return False

        if "动态" in type_names:
            return False
        
        type_name = type_names[0] if type_names else ""
        message_title, markdown_text = self._format_message(items, type_names)
        
        payload = {
            "msg_type": type_name,
            "title": message_title,
            "content": {"text": markdown_text}
        }
        
        return self._send_notification(url, payload, type_name, items)

    def _send_reminder(self) -> bool:
        """Send reminder notification when no updates in REMINDER_HOURS."""
        url = self.config.webhook_url
        if not url:
            return False
        
        time_str = self._get_beijing_time_str()
        message_title = "马前卒在过去的二十四小时没有更新任何内容"
        markdown_text = f"最后检查时间：{time_str}"
        
        payload = {
            "msg_type": "text",
            "title": message_title,
            "content": {"text": markdown_text}
        }
        
        return self._send_notification(url, payload, "reminder", [])

    def _check_and_send_reminder(self, state: Dict) -> None:
        """Check if reminder should be sent and send it if needed."""
        try:
            last_notification_str = state.get("last_notification_time") or state.get("last_check")
            if not last_notification_str:
                logger.debug("No last_notification_time or last_check found, skipping reminder check")
                return
            
            logger.debug(f"Checking reminder condition. Last notification time: {last_notification_str}")
            
            # Parse last notification time, handling both with and without timezone
            try:
                last_notification = datetime.fromisoformat(last_notification_str)
                # If no timezone info, assume it's UTC
                if last_notification.tzinfo is None:
                    last_notification = last_notification.replace(tzinfo=timezone.utc)
                    logger.debug(f"Parsed last_notification (no tz): {last_notification_str} -> {last_notification} (UTC)")
                else:
                    logger.debug(f"Parsed last_notification (with tz): {last_notification}")
            except ValueError as e:
                logger.error(f"Failed to parse last_notification_time '{last_notification_str}': {e}")
                return
            
            # Get current time in UTC for consistent comparison
            now = datetime.now(timezone.utc)
            logger.debug(f"Current time (UTC): {now}")
            
            # Calculate time difference
            time_diff = now - last_notification
            hours_passed = time_diff.total_seconds() / 3600
            logger.debug(f"Time difference: {time_diff.total_seconds()} seconds ({hours_passed:.2f} hours)")
            logger.debug(f"Reminder threshold: {self.REMINDER_HOURS} hours")
            
            if time_diff.total_seconds() >= self.REMINDER_HOURS * 3600:
                logger.info(f"Reminder condition met: {hours_passed:.2f} hours >= {self.REMINDER_HOURS} hours")
                if self._send_reminder():
                    state["last_notification_time"] = now.isoformat()
                    logger.info("Reminder notification sent: no updates in 8 hours")
                else:
                    logger.warning("Failed to send reminder notification")
            else:
                logger.debug(f"Reminder condition not met: {hours_passed:.2f} hours < {self.REMINDER_HOURS} hours")
        except Exception as e:
            logger.error(f"Error checking reminder condition: {e}", exc_info=True)

    # ==================== Main Monitoring Logic ====================

    def _process_items(self, data: Dict, type_name: str, seen: Set[str]) -> List[Dict]:
        """Process RSS items and return new items."""
        items = data.get("items", [])
        if not isinstance(items, list):
            logger.warning(f"Invalid items format for type {type_name}")
            return []
        
        new_items = []
        for item in items:
            if not isinstance(item, dict):
                logger.warning(f"Invalid item format in type {type_name}, skipping")
                continue
            
            item_id = self._get_item_id(item)
            if not item_id:
                logger.warning("Item missing both id and url, skipping")
                continue
            
            if item_id not in seen:
                title = self._remove_user_prefix(item.get("title", ""))[:50]
                logger.info(f"New {type_name}: {title}")
                
                new_items.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content_html": item.get("content_html", ""),
                    "content_text": item.get("content_text", ""),
                    "summary": item.get("summary", "")
                })
                seen.add(item_id)
        
        return new_items

    def _notify_new_items(self, new_items_by_type: Dict[str, List[Dict]], state: Dict) -> bool:
        """Send notifications for new items grouped by type."""
        notification_sent = False
        for type_name, items in new_items_by_type.items():
            if items:
                type_names = [type_name] * len(items)
                if self.send_webhook(items, type_names):
                    notification_sent = True
        
        if notification_sent:
            # Use UTC timezone for consistency
            state["last_notification_time"] = datetime.now(timezone.utc).isoformat()
            logger.debug(f"Updated last_notification_time: {state['last_notification_time']}")
        
        return notification_sent

    def _send_debug_notification(self, state: Dict) -> None:
        """Send debug notification when in debug mode."""
        if not self.config.webhook_url:
            logger.warning("WEBHOOK_URL not configured, skipping debug notification")
            return
        
        time_str = self._get_beijing_time_str()
        message_title = f"[DEBUG] 监控检查完成 - {time_str}"
        markdown_text = f"调试模式：监控脚本已执行\n检查时间：{time_str}\n状态：未发现新内容"
        
        payload = {
            "msg_type": "text",
            "title": message_title,
            "content": {"text": markdown_text}
        }
        
        if self._send_notification(self.config.webhook_url, payload, "debug", []):
            state["last_notification_time"] = datetime.now(timezone.utc).isoformat()
            logger.info("Debug notification sent successfully")

    def check_updates(self) -> int:
        """Check for updates and return count of new items found."""
        logger.info(f"Checking updates for {self.config.user_name}...")
        if self.config.debug_mode:
            logger.info("DEBUG MODE ENABLED - will send notification even if no new items found")
        
        state = self.load_state()
        logger.debug(f"Loaded state: last_notification_time={state.get('last_notification_time')}, last_check={state.get('last_check')}")
        
        seen: Set[str] = set(state.get("seen_ids", []))
        new_items_by_type: Dict[str, List[Dict]] = {}
        
        # Fetch and process items from each route
        for route, type_name in ROUTE_EN_TO_CN.items():
            data = self.fetch_rss(route)
            if not data:
                continue
            
            new_items = self._process_items(data, type_name, seen)
            if new_items:
                new_items_by_type[type_name] = new_items
        
        # Send notifications
        new_count = sum(len(items) for items in new_items_by_type.values())
        logger.debug(f"Found {new_count} new items")
        
        notification_sent = self._notify_new_items(new_items_by_type, state)
        
        # In debug mode, send notification even if no new items
        if self.config.debug_mode and new_count == 0:
            logger.info("Debug mode: sending notification even though no new items found")
            self._send_debug_notification(state)
        elif new_count == 0:
            # Send reminder if no new content (normal mode)
            logger.debug("No new items found, checking reminder condition")
            self._check_and_send_reminder(state)
        else:
            logger.debug(f"New items found ({new_count}), skipping reminder check")
        
        # Update and save state
        self._update_seen_ids(state, seen)
        self.save_state(state)
        
        logger.info(f"Completed, found {new_count} new items")
        return new_count


def main() -> None:
    """Main entry point."""
    start_time = datetime.now(timezone.utc)
    
    # Detect trigger source
    # Ofelia executes via docker exec, so check if we're in a scheduled context
    # We can check parent process or just assume scheduled if running in container
    trigger_source = "Manual execution"
    if os.getenv('OFELIA_JOB_NAME'):
        trigger_source = "Ofelia scheduler"
    elif os.path.exists('/.dockerenv'):
        # Running in Docker container, likely scheduled by Ofelia
        # Check if we have a predictable schedule pattern (every 5 minutes)
        trigger_source = "Ofelia scheduler (detected)"
    
    logger.info("=" * 60)
    logger.info(f"Monitor script started at {start_time.isoformat()}")
    logger.info(f"Triggered by: {trigger_source}")
    logger.info("=" * 60)
    
    try:
        config = Config.from_env()
        monitor = Monitor(config)
        new_count = monitor.check_updates()
        
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        logger.info("=" * 60)
        logger.info(f"Monitor script completed in {duration:.2f} seconds")
        logger.info(f"Finished at {end_time.isoformat()}")
        logger.info("=" * 60)
    except Exception as e:
        end_time = datetime.now(timezone.utc)
        logger.error(f"Monitor script failed: {e}", exc_info=True)
        logger.error(f"Failed at {end_time.isoformat()}")
        raise


if __name__ == "__main__":
    main()
