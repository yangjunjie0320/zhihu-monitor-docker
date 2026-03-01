#!/usr/bin/env python3
"""Parse Netscape format cookies file and output as cookie string."""

import sys
from pathlib import Path

# Add parent directory to path to import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cookie_manager import CookieManager


def main():
    if len(sys.argv) < 2:
        print("Usage: parse_cookies.py <cookie_file>", file=sys.stderr)
        sys.exit(1)

    cookie_file = Path(sys.argv[1])
    manager = CookieManager(cookie_file)
    print(manager.parse_cookies())


if __name__ == "__main__":
    main()
