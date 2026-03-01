"""Constants and enums for Zhihu monitor."""

from enum import Enum


class ContentType(Enum):
    """Zhihu content types."""

    ANSWER = ("answers", "回答")
    PIN = ("pins", "想法")

    @property
    def route(self) -> str:
        """Get English route name."""
        return self.value[0]

    @property
    def display_name(self) -> str:
        """Get Chinese display name."""
        return self.value[1]

    @classmethod
    def from_route(cls, route: str) -> "ContentType":
        """Get content type from route name."""
        for content_type in cls:
            if content_type.route == route:
                return content_type
        raise ValueError(f"Unknown route: {route}")

    @classmethod
    def from_display_name(cls, display_name: str) -> "ContentType":
        """Get content type from display name."""
        for content_type in cls:
            if content_type.display_name == display_name:
                return content_type
        raise ValueError(f"Unknown display name: {display_name}")


class NotificationType(Enum):
    """Types of notifications."""

    NEW_ANSWER = "回答"
    NEW_PIN = "想法"
    REMINDER = "reminder"
    ERROR = "error"
    COOKIE_EXPIRY = "cookie_expiry"
    DEBUG = "debug"


# HTML entity mapping for decoding
HTML_ENTITIES = {
    '&nbsp;': ' ',
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&quot;': '"',
    '&#39;': "'"
}

# Time constants
REMINDER_INTERVAL_HOURS = 24
ERROR_REPORT_INTERVAL_HOURS = 24
MAX_SEEN_IDS = 1000
