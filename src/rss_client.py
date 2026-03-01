"""RSS client for fetching Zhihu content."""

import json
import logging
from typing import Dict, List, Optional, Tuple

import requests

from .constants import ContentType
from .models import Config

logger = logging.getLogger(__name__)


class RSSClient:
    """Client for fetching RSS feeds from RSSHub."""

    def __init__(self, config: Config):
        """Initialize RSS client.

        Args:
            config: Monitor configuration
        """
        self.config = config

    def fetch(self, content_type: ContentType) -> Tuple[Optional[Dict], Optional[str]]:
        """Fetch RSS data from RSSHub for given content type.

        Args:
            content_type: Type of content to fetch

        Returns:
            Tuple of (data dict or None, error message or None)
        """
        url = f"{self.config.rsshub_base}/zhihu/people/{content_type.route}/{self.config.user_id}?format=json"

        try:
            resp = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            if not isinstance(data, dict):
                error_msg = f"Invalid response format for {content_type.display_name}"
                logger.warning(error_msg)
                return None, error_msg

            return data, None

        except requests.exceptions.Timeout:
            error_msg = f"Request timeout for {content_type.display_name}"
            logger.error(error_msg)
            return None, error_msg

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error for {content_type.display_name}: {e}"
            logger.error(error_msg)
            return None, error_msg

        except (requests.exceptions.RequestException, json.JSONDecodeError, Exception) as e:
            error_msg = f"Error fetching RSS for {content_type.display_name}: {e}"
            logger.error(error_msg)
            return None, error_msg

    def fetch_all(self) -> Dict[ContentType, Tuple[Optional[Dict], Optional[str]]]:
        """Fetch RSS data for all content types.

        Returns:
            Dict mapping content type to (data, error) tuple
        """
        results = {}
        for content_type in ContentType:
            data, error = self.fetch(content_type)
            results[content_type] = (data, error)
        return results
