#!/usr/bin/env python3
"""Test script to verify all modules can be imported."""

import sys


def test_imports():
    """Test that all modules can be imported."""
    try:
        print("Testing imports...")

        print("  - src.constants")
        from src import constants

        print("  - src.models")
        from src import models

        print("  - src.time_utils")
        from src import time_utils

        print("  - src.config")
        from src import config

        print("  - src.text_processor")
        from src import text_processor

        print("  - src.state_manager")
        from src import state_manager

        print("  - src.rss_client")
        from src import rss_client

        print("  - src.webhook_client")
        from src import webhook_client

        print("  - src.monitor")
        from src import monitor

        print("  - src.logging_config")
        from src import logging_config

        print("\n✅ All imports successful!")
        return True

    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        return False


def test_basic_functionality():
    """Test basic functionality."""
    try:
        print("\nTesting basic functionality...")

        from src.constants import ContentType
        from src.models import Config, Item, State
        from src.time_utils import TimeUtils
        from src.text_processor import TextProcessor

        # Test ContentType
        print("  - ContentType enum")
        assert ContentType.ANSWER.route == "answers"
        assert ContentType.PIN.display_name == "想法"

        # Test TimeUtils
        print("  - TimeUtils")
        now = TimeUtils.now_utc()
        beijing_str = TimeUtils.beijing_now_str()
        assert isinstance(beijing_str, str)

        # Test TextProcessor
        print("  - TextProcessor")
        processor = TextProcessor()
        assert processor.has_image("<img src='test.jpg'>") is True
        assert processor.has_image("No image here") is False

        # Test Config
        print("  - Config model")
        config = Config(webhook_url="https://example.com/webhook")
        assert config.user_id == "shui-qian-xiao-xi"

        # Test Item
        print("  - Item model")
        item = Item(
            title="Test",
            url="https://example.com",
            content_html="<p>Test</p>"
        )
        assert item.title == "Test"
        assert item.to_dict()["title"] == "Test"

        # Test State
        print("  - State model")
        state = State()
        assert state.seen_ids == []

        print("\n✅ All basic tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_imports() and test_basic_functionality()
    sys.exit(0 if success else 1)
