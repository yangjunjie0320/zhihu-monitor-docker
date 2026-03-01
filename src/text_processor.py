"""Text processing utilities."""

import re

from .constants import HTML_ENTITIES


class TextProcessor:
    """Text processing and extraction utilities."""

    @staticmethod
    def has_image(html_content: str) -> bool:
        """Check if HTML content contains images."""
        if not html_content:
            return False
        return bool(re.search(r'<img[^>]*>', html_content, re.IGNORECASE))

    @staticmethod
    def clean_text(text: str) -> str:
        """Clean extracted text by removing HTML artifacts and normalizing whitespace."""
        if not text:
            return ""

        # Remove HTML tags and attributes
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+[a-z-]+="[^"]*"', '', text)

        # Decode HTML entities
        for entity, char in HTML_ENTITIES.items():
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
        return TextProcessor.clean_text(html_content)

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

    @staticmethod
    def remove_prefix(text: str, prefix: str) -> str:
        """Remove prefix from text."""
        if not text:
            return text
        if text.startswith(prefix):
            return text[len(prefix):].strip()
        return text
