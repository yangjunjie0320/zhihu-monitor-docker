#!/usr/bin/env python3
"""Parse Netscape format cookies file and output as cookie string."""
import sys
from pathlib import Path

IMPORTANT_COOKIES = {
    'SESSIONID', 'JOID', 'osd', '_xsrf', '_zap', 'd_c0', 'z_c0',
    '__zse_ck', 'HMACCOUNT', 'Hm_lvt_98beee57fd2ef70ccdd5ca52b9740c49'
}


def parse_netscape_cookies(file_path: str) -> str:
    """Parse cookies from Netscape format file."""
    cookies = []
    path = Path(file_path)
    if not path.exists():
        return ""

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) >= 7:
            name, value = parts[5], parts[6]
            if name in IMPORTANT_COOKIES or any(kw in name.lower() for kw in ['session', 'token', 'auth']):
                cookies.append(f"{name}={value}")

    return "; ".join(cookies)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: parse_cookies.py <cookie_file>", file=sys.stderr)
        sys.exit(1)
    print(parse_netscape_cookies(sys.argv[1]))
