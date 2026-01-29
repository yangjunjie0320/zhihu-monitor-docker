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
import logging.handlers
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, LOG_LEVEL, logging.INFO)

# Setup logging with file rotation (keep 15 days)
log_file = Path(os.getenv("LOG_FILE", "/data/monitor.log"))
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
logger = logging.getLogger(__name__)
logger.setLevel(log_level)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Prevent duplicate logs
logger.propagate = False

def parse_netscape_cookies(cookie_file: Path) -> str:
    """Parse Netscape cookie file and convert to cookie string format.
    
    Args:
        cookie_file: Path to Netscape cookie file
        
    Returns:
        Cookie string in format: "name1=value1; name2=value2; ..."
    """
    if not cookie_file.exists():
        logger.warning(f"Cookie file not found: {cookie_file}")
        return ""
    
    cookies = []
    important_cookies = {
        'SESSIONID', 'JOID', 'osd', '_xsrf', '_zap', 'd_c0', 'z_c0',
        '__zse_ck', 'HMACCOUNT', 'Hm_lvt_98beee57fd2ef70ccdd5ca52b9740c49'
    }
    
    try:
        with open(cookie_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Netscape format: domain, flag, path, secure, expiration, name, value
                parts = line.split('\t')
                if len(parts) >= 7:
                    name = parts[5]
                    value = parts[6]
                    # Only include important cookies
                    if name in important_cookies or any(key in name.lower() for key in ['session', 'auth', 'token']):
                        cookies.append(f"{name}={value}")
        
        cookie_string = '; '.join(cookies)
        logger.debug(f"Parsed {len(cookies)} cookies from {cookie_file}")
        return cookie_string
    except Exception as e:
        logger.error(f"Failed to parse cookie file {cookie_file}: {e}")
        return ""

def get_cookie_file_mtime(cookie_file: Path) -> Optional[datetime]:
    """Get modification time of cookie file."""
    if cookie_file.exists():
        return datetime.fromtimestamp(cookie_file.stat().st_mtime, tz=timezone.utc)
    return None

@dataclass
class Config:
    """Configuration for Zhihu monitor."""
    user_id: str
    user_name: str
    rsshub_base: str
    webhook_url: str
    state_file: Path
    debug_mode: bool
    cookie_file: Path
    cookie_expiry_days: int
    cookie_reminder_interval_days: int

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        debug_mode = os.getenv("DEBUG_MODE", "").lower() in ("true", "1", "yes", "on")
        cookie_file = Path(os.getenv("COOKIE_FILE", "/data/cookies.txt"))
        cookie_expiry_days = int(os.getenv("COOKIE_EXPIRY_DAYS", "15"))
        cookie_reminder_interval_days = int(os.getenv("COOKIE_REMINDER_INTERVAL_DAYS", "5"))
        
        return cls(
            user_id=os.getenv("ZHIHU_USER_ID", "shui-qian-xiao-xi"),
            user_name=os.getenv("ZHIHU_USER_NAME", "马前卒official"),
            rsshub_base=os.getenv("RSSHUB_BASE", "http://rsshub:1200"),
            webhook_url=os.getenv("WEBHOOK_URL", ""),
            state_file=Path(os.getenv("STATE_FILE", "/data/state.json")),
            debug_mode=debug_mode,
            cookie_file=cookie_file,
            cookie_expiry_days=cookie_expiry_days,
            cookie_reminder_interval_days=cookie_reminder_interval_days,
        )

ROUTE_CN_TO_EN = {"回答": "answers", "想法": "pins"}
ROUTE_EN_TO_CN = {"answers": "回答", "pins": "想法"}

class Monitor:
    """Monitor Zhihu user updates and send notifications via webhook."""
    REMINDER_HOURS = 24
    MAX_SEEN_IDS = 1000
    ERROR_REPORT_INTERVAL_HOURS = 24

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

    def fetch_rss(self, route: str) -> tuple[Optional[Dict], Optional[str]]:
        """Fetch RSS data from RSSHub for given route.
        Returns: (data, error_message)
        """
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
                error_msg = f"Invalid response format for route {route}"
                logger.warning(error_msg)
                return None, error_msg
            return data, None
        except requests.exceptions.Timeout:
            error_msg = f"Request timeout for route {route}"
            logger.error(error_msg)
            return None, error_msg
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error for route {route}: {e}"
            logger.error(error_msg)
            return None, error_msg
        except (requests.exceptions.RequestException, json.JSONDecodeError, Exception) as e:
            error_msg = f"Error fetching RSS for route {route}: {e}"
            logger.error(error_msg)
            return None, error_msg

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

    def _check_cookie_expiry(self, state: Dict) -> None:
        """Check cookie file expiry and send reminder if needed."""
        cookie_mtime = get_cookie_file_mtime(self.config.cookie_file)
        if not cookie_mtime:
            logger.warning(f"Cookie file not found: {self.config.cookie_file}")
            return
        
        # Calculate expiry date
        expiry_date = cookie_mtime + timedelta(days=self.config.cookie_expiry_days)
        now = datetime.now(timezone.utc)
        days_until_expiry = (expiry_date - now).days
        
        # Check if we should send reminder
        last_reminder_str = state.get("last_cookie_reminder_time")
        should_send_reminder = False
        
        if not last_reminder_str:
            # First reminder check
            should_send_reminder = True
        else:
            try:
                last_reminder = datetime.fromisoformat(last_reminder_str)
                if last_reminder.tzinfo is None:
                    last_reminder = last_reminder.replace(tzinfo=timezone.utc)
                
                days_since_last_reminder = (now - last_reminder).days
                if days_since_last_reminder >= self.config.cookie_reminder_interval_days:
                    should_send_reminder = True
            except (ValueError, Exception) as e:
                logger.error(f"Failed to parse last_cookie_reminder_time: {e}")
                should_send_reminder = True
        
        if should_send_reminder and days_until_expiry > 0:
            self._send_cookie_expiry_reminder(cookie_mtime, expiry_date, days_until_expiry, state)
        elif days_until_expiry <= 0:
            logger.warning(f"Cookie file has expired! Last modified: {cookie_mtime}, Expiry: {expiry_date}")

    def _send_cookie_expiry_reminder(self, cookie_mtime: datetime, expiry_date: datetime, 
                                     days_until_expiry: int, state: Dict) -> None:
        """Send cookie expiry reminder notification."""
        if not self.config.webhook_url:
            logger.warning("WEBHOOK_URL not configured, skipping cookie reminder")
            return
        
        beijing_tz = timezone(timedelta(hours=8))
        cookie_mtime_beijing = cookie_mtime.astimezone(beijing_tz)
        expiry_date_beijing = expiry_date.astimezone(beijing_tz)
        time_str = self._get_beijing_time_str()
        
        message_title = f"[提醒] Cookies 文件即将过期 - {time_str}"
        markdown_text = (
            f"Cookies 文件过期提醒\n\n"
            f"文件路径：{self.config.cookie_file}\n"
            f"最后修改时间：{cookie_mtime_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)\n"
            f"预计过期时间：{expiry_date_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)\n"
            f"剩余天数：{days_until_expiry} 天\n\n"
            f"请及时更新 cookies 文件以避免服务中断。\n"
            f"提醒频率：每 {self.config.cookie_reminder_interval_days} 天提醒一次"
        )
        
        payload = {
            "msg_type": "text",
            "title": message_title,
            "content": {"text": markdown_text}
        }
        
        if self._send_notification(self.config.webhook_url, payload, "cookie_reminder", []):
            state["last_cookie_reminder_time"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"Cookie expiry reminder sent: {days_until_expiry} days until expiry")

    def _should_send_error_report(self, state: Dict) -> bool:
        """Check if error report should be sent (every 24 hours)."""
        last_error_report_str = state.get("last_error_report_time")
        if not last_error_report_str:
            # No previous error report, should send
            return True
        
        try:
            last_error_report = datetime.fromisoformat(last_error_report_str)
            if last_error_report.tzinfo is None:
                last_error_report = last_error_report.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            time_diff = now - last_error_report
            hours_passed = time_diff.total_seconds() / 3600
            
            logger.debug(f"Last error report: {last_error_report_str}, hours passed: {hours_passed:.2f}")
            
            return hours_passed >= self.ERROR_REPORT_INTERVAL_HOURS
        except (ValueError, Exception) as e:
            logger.error(f"Failed to parse last_error_report_time: {e}")
            return True  # If parsing fails, send report to be safe

    def _send_error_notification(self, errors: List[str], state: Dict) -> bool:
        """Send error notification when errors occur (only if 24 hours have passed since last report).
        Returns True if notification was sent, False otherwise.
        """
        if not self.config.webhook_url:
            logger.warning("WEBHOOK_URL not configured, skipping error notification")
            return False
        
        if not errors:
            return False
        
        # Check if we should send error report (every 24 hours)
        if not self._should_send_error_report(state):
            last_error_report_str = state.get("last_error_report_time")
            if last_error_report_str:
                try:
                    last_error_report = datetime.fromisoformat(last_error_report_str)
                    if last_error_report.tzinfo is None:
                        last_error_report = last_error_report.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    hours_passed = (now - last_error_report).total_seconds() / 3600
                    hours_until_next = self.ERROR_REPORT_INTERVAL_HOURS - hours_passed
                    logger.info(f"Errors detected but skipping report (last report was {hours_passed:.1f}h ago, next report in {hours_until_next:.1f}h)")
                except (ValueError, Exception):
                    logger.info("Errors detected but skipping report (last report was less than 24h ago)")
            else:
                logger.info("Errors detected but skipping report (last report was less than 24h ago)")
            return False
        
        time_str = self._get_beijing_time_str()
        message_title = f"[错误] 监控检查失败 - {time_str}"
        
        error_list = "\n".join([f"- {error}" for error in errors])
        markdown_text = f"监控脚本执行时遇到错误：\n\n{error_list}\n\n检查时间：{time_str}\n\n错误报告每24小时发送一次。"
        
        payload = {
            "msg_type": "text",
            "title": message_title,
            "content": {"text": markdown_text}
        }
        
        if self._send_notification(self.config.webhook_url, payload, "error", []):
            state["last_error_report_time"] = datetime.now(timezone.utc).isoformat()
            logger.info("Error notification sent successfully")
            return True
        
        return False

    def check_updates(self) -> int:
        """Check for updates and return count of new items found."""
        logger.info(f"Checking updates for {self.config.user_name}...")
        if self.config.debug_mode:
            logger.info("DEBUG MODE ENABLED - will send notification even if no new items found")
        
        state = self.load_state()
        logger.debug(f"Loaded state: last_notification_time={state.get('last_notification_time')}, last_check={state.get('last_check')}")
        
        seen: Set[str] = set(state.get("seen_ids", []))
        new_items_by_type: Dict[str, List[Dict]] = {}
        errors: List[str] = []  # Track errors
        
        # Fetch and process items from each route
        for route, type_name in ROUTE_EN_TO_CN.items():
            data, error = self.fetch_rss(route)
            if error:
                errors.append(f"{type_name}: {error}")
            if not data:
                continue
            
            new_items = self._process_items(data, type_name, seen)
            if new_items:
                new_items_by_type[type_name] = new_items
        
        # Handle errors
        has_errors = len(errors) > 0
        if has_errors:
            logger.warning(f"Encountered {len(errors)} error(s) during check")
            error_report_sent = self._send_error_notification(errors, state)
            if error_report_sent:
                logger.info("Error report sent, normal notifications will be suppressed until errors are resolved")
        else:
            # No errors, clear error report time if it exists
            if "last_error_report_time" in state:
                logger.info("All errors resolved, clearing error report time")
                del state["last_error_report_time"]
        
        # Send notifications only if no errors (errors suppress normal notifications)
        new_count = sum(len(items) for items in new_items_by_type.values())
        logger.debug(f"Found {new_count} new items")
        
        if has_errors:
            logger.info("Errors detected, skipping normal notifications")
            notification_sent = False
        else:
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
        
        # Check cookie expiry and send reminder if needed
        self._check_cookie_expiry(state)
        
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
