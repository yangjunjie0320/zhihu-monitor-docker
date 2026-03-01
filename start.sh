#!/bin/bash
set -e
cd "$(dirname "$0")"

# Parse cookies from file
COOKIE_FILE="${COOKIE_FILE:-../cookies.txt}"
if [ -f "$COOKIE_FILE" ]; then
    export ZHIHU_COOKIES=$(python3 scripts/parse_cookies.py "$COOKIE_FILE")
    echo "Cookies parsed from $COOKIE_FILE"
else
    echo "Warning: Cookie file not found: $COOKIE_FILE"
fi

# Start services
docker compose up -d --build "$@"
