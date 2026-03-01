"""Webhook client for sending notifications."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

from .constants import ContentType
from .models import Config, Item
from .text_processor import TextProcessor
from .time_utils import TimeUtils

logger = logging.getLogger(__name__)


class WebhookClient:
    """Client for sending webhook notifications."""

    def __init__(self, config: Config):
        """Initialize webhook client.

        Args:
            config: Monitor configuration
        """
        self.config = config
        self.text_processor = TextProcessor()

    def _send_request(self, url: str, payload: Dict, timeout: int = 10) -> requests.Response:
        """Send webhook HTTP request.

        Args:
            url: Webhook URL
            payload: JSON payload
            timeout: Request timeout in seconds

        Returns:
            Response object

        Raises:
            requests.exceptions.RequestException: On request error
        """
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response

    def _save_debug_info(
        self,
        url: str,
        payload: Dict,
        type_name: str,
        items: List[Item],
        response: Optional[requests.Response] = None,
        error: Optional[str] = None
    ) -> None:
        """Save debug information for webhook requests.

        Args:
            url: Webhook URL
            payload: Sent payload
            type_name: Notification type name
            items: List of items
            response: Response object if successful
            error: Error message if failed
        """
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

            debug_record["items"] = [item.to_dict() for item in items]

            history[msg_type] = debug_record
            debug_file.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(history, ensure_ascii=False, indent=2)
            debug_file.write_text(content, encoding="utf-8")

            logger.debug(f"Debug info saved for msg_type: {msg_type}")

        except Exception as e:
            logger.error(f"Failed to save debug info: {e}")

    def _send_notification(
        self,
        url: str,
        payload: Dict,
        type_name: str,
        items: List[Item]
    ) -> bool:
        """Send notification webhook and save debug info.

        Args:
            url: Webhook URL
            payload: JSON payload
            type_name: Notification type name
            items: List of items

        Returns:
            True if successful, False otherwise
        """
        response = None
        error = None

        try:
            response = self._send_request(url, payload)
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

    def _format_item_markdown(self, item: Item, content_type: ContentType) -> str:
        """Format a single item as Markdown line.

        Args:
            item: Item to format
            content_type: Type of content

        Returns:
            Formatted markdown string
        """
        title = self.text_processor.remove_prefix(
            item.title,
            f"{self.config.user_name}："
        )
        link = item.url

        if item.summary:
            content_preview = self.text_processor.extract_first_n_chars(item.summary, 50)
            has_img = self.text_processor.has_image(item.content_html)
        else:
            content_text = self.text_processor.extract_text_from_html(
                item.content_html or item.content_text
            )
            content_preview = self.text_processor.extract_first_n_chars(content_text, 50)
            has_img = self.text_processor.has_image(item.content_html or item.content_text)

        if content_preview:
            prefixes_to_remove = [
                f"New {content_type.display_name}: ",
                f"New {content_type.display_name}: {self.config.user_name}：",
                f"New {content_type.display_name}: {self.config.user_name}:",
                f"{self.config.user_name}：",
            ]
            for prefix in prefixes_to_remove:
                content_preview = self.text_processor.remove_prefix(content_preview, prefix)

        markdown_text = f"- [{title}]({link})"
        if content_type != ContentType.PIN:  # Don't show preview for pins
            if content_preview:
                markdown_text += f" {content_preview}"
            if has_img:
                markdown_text += " [图片]"

        return markdown_text

    def _format_message(
        self,
        items: List[Item],
        content_types: List[ContentType]
    ) -> tuple[str, str]:
        """Format webhook message title and content.

        Args:
            items: List of items
            content_types: List of content types (one per item)

        Returns:
            Tuple of (message_title, markdown_text)
        """
        content_type = content_types[0] if content_types else ContentType.ANSWER

        type_name_cn_map = {
            ContentType.ANSWER: "新回答",
            ContentType.PIN: "新想法"
        }
        type_name_cn = type_name_cn_map.get(content_type, content_type.display_name)

        time_str = TimeUtils.beijing_now_str()
        message_title = f"{type_name_cn} {len(items)}条 获取时间：{time_str}"

        markdown_lines = [
            self._format_item_markdown(item, item_type)
            for item, item_type in zip(items, content_types)
        ]
        markdown_text = "\n".join(markdown_lines)

        user_prefix = f"{self.config.user_name}："
        markdown_text = markdown_text.replace(user_prefix, "")

        return message_title, markdown_text

    def send_new_items(
        self,
        items: List[Item],
        content_types: List[ContentType]
    ) -> bool:
        """Send notification for new items.

        Args:
            items: List of new items
            content_types: List of content types (one per item)

        Returns:
            True if successful, False otherwise
        """
        if not self.config.webhook_url or not items:
            if not self.config.webhook_url:
                logger.warning("WEBHOOK_URL not configured, skipping notification")
            return False

        content_type = content_types[0] if content_types else ContentType.ANSWER
        message_title, markdown_text = self._format_message(items, content_types)

        payload = {
            "msg_type": content_type.display_name,
            "title": message_title,
            "content": {"text": markdown_text}
        }

        return self._send_notification(
            self.config.webhook_url,
            payload,
            content_type.display_name,
            items
        )

    def send_reminder(self) -> bool:
        """Send reminder notification when no updates for configured hours.

        Returns:
            True if successful, False otherwise
        """
        if not self.config.webhook_url:
            return False

        time_str = TimeUtils.beijing_now_str()
        message_title = f"{self.config.user_name}在过去的{self.config.reminder_hours}小时没有更新任何内容"
        markdown_text = f"最后检查时间：{time_str}"

        payload = {
            "msg_type": "text",
            "title": message_title,
            "content": {"text": markdown_text}
        }

        return self._send_notification(
            self.config.webhook_url,
            payload,
            "reminder",
            []
        )

    def send_debug_notification(self) -> bool:
        """Send debug notification when in debug mode.

        Returns:
            True if successful, False otherwise
        """
        if not self.config.webhook_url:
            logger.warning("WEBHOOK_URL not configured, skipping debug notification")
            return False

        time_str = TimeUtils.beijing_now_str()
        message_title = f"[DEBUG] 监控检查完成 - {time_str}"
        markdown_text = f"调试模式：监控脚本已执行\n检查时间：{time_str}\n状态：未发现新内容"

        payload = {
            "msg_type": "text",
            "title": message_title,
            "content": {"text": markdown_text}
        }

        return self._send_notification(
            self.config.webhook_url,
            payload,
            "debug",
            []
        )

    def send_error_report(self, errors: List[str]) -> bool:
        """Send error notification.

        Args:
            errors: List of error messages

        Returns:
            True if successful, False otherwise
        """
        if not self.config.webhook_url or not errors:
            if not self.config.webhook_url:
                logger.warning("WEBHOOK_URL not configured, skipping error notification")
            return False

        time_str = TimeUtils.beijing_now_str()
        message_title = f"[错误] 监控检查失败 - {time_str}"

        error_list = "\n".join([f"- {error}" for error in errors])
        markdown_text = (
            f"监控脚本执行时遇到错误：\n\n{error_list}\n\n"
            f"检查时间：{time_str}\n\n"
            f"错误报告每{self.config.error_report_interval_hours}小时发送一次。"
        )

        payload = {
            "msg_type": "text",
            "title": message_title,
            "content": {"text": markdown_text}
        }

        return self._send_notification(
            self.config.webhook_url,
            payload,
            "error",
            []
        )

    def send_cookie_expiry_reminder(
        self,
        cookie_mtime: datetime,
        expiry_date: datetime,
        days_until_expiry: int
    ) -> bool:
        """Send cookie expiry reminder notification.

        Args:
            cookie_mtime: Cookie file modification time
            expiry_date: Cookie expiry date
            days_until_expiry: Days until expiry

        Returns:
            True if successful, False otherwise
        """
        if not self.config.webhook_url:
            logger.warning("WEBHOOK_URL not configured, skipping cookie reminder")
            return False

        cookie_mtime_beijing = TimeUtils.to_beijing(cookie_mtime)
        expiry_date_beijing = TimeUtils.to_beijing(expiry_date)
        time_str = TimeUtils.beijing_now_str()

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

        return self._send_notification(
            self.config.webhook_url,
            payload,
            "cookie_reminder",
            []
        )
