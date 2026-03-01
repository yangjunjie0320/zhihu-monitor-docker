"""Cookie management for Zhihu monitor."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from .time_utils import TimeUtils

logger = logging.getLogger(__name__)

# Important Zhihu cookies for authentication
IMPORTANT_COOKIES = {
    'SESSIONID', 'JOID', 'osd', '_xsrf', '_zap', 'd_c0', 'z_c0',
    '__zse_ck', 'HMACCOUNT', 'Hm_lvt_98beee57fd2ef70ccdd5ca52b9740c49'
}

# Keywords that indicate important cookies
IMPORTANT_COOKIE_KEYWORDS = {'session', 'token', 'auth'}


@dataclass
class CookieStatus:
    """Cookie file status information."""

    exists: bool
    mtime: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    days_until_expiry: Optional[int] = None
    is_expired: bool = False


class CookieManager:
    """Manage cookie file parsing and expiry checking."""

    def __init__(self, cookie_file: Path, expiry_days: int = 15):
        """Initialize cookie manager.

        Args:
            cookie_file: Path to the Netscape format cookie file
            expiry_days: Number of days until cookies are considered expired
        """
        self.cookie_file = cookie_file
        self.expiry_days = expiry_days

    def parse_cookies(self) -> str:
        """Parse cookies from Netscape format file.

        Returns:
            Cookie string in "name=value; name2=value2" format
        """
        if not self.cookie_file.exists():
            logger.warning(f"Cookie file not found: {self.cookie_file}")
            return ""

        cookies: List[str] = []
        try:
            for line in self.cookie_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split('\t')
                if len(parts) >= 7:
                    name, value = parts[5], parts[6]
                    if self._is_important_cookie(name):
                        cookies.append(f"{name}={value}")
        except Exception as e:
            logger.error(f"Error parsing cookie file: {e}")
            return ""

        return "; ".join(cookies)

    def _is_important_cookie(self, name: str) -> bool:
        """Check if a cookie is important for authentication.

        Args:
            name: Cookie name

        Returns:
            True if the cookie is important
        """
        if name in IMPORTANT_COOKIES:
            return True
        name_lower = name.lower()
        return any(kw in name_lower for kw in IMPORTANT_COOKIE_KEYWORDS)

    def get_status(self) -> CookieStatus:
        """Get current cookie file status.

        Returns:
            CookieStatus with expiry information
        """
        if not self.cookie_file.exists():
            return CookieStatus(exists=False)

        now = TimeUtils.now_utc()
        mtime = datetime.fromtimestamp(
            self.cookie_file.stat().st_mtime,
            tz=now.tzinfo
        )
        expiry_date = mtime + timedelta(days=self.expiry_days)
        days_until_expiry = (expiry_date - now).days
        is_expired = days_until_expiry <= 0

        return CookieStatus(
            exists=True,
            mtime=mtime,
            expiry_date=expiry_date,
            days_until_expiry=days_until_expiry,
            is_expired=is_expired
        )

    def check_expiry(self) -> Optional[CookieStatus]:
        """Check if cookie file is expiring or expired.

        Returns:
            CookieStatus if file exists, None otherwise
        """
        status = self.get_status()

        if not status.exists:
            logger.warning(f"Cookie file not found: {self.cookie_file}")
            return None

        if status.is_expired:
            logger.warning(
                f"Cookie file has expired! Last modified: {status.mtime}, "
                f"Expiry: {status.expiry_date}"
            )
        elif status.days_until_expiry is not None and status.days_until_expiry <= 3:
            logger.warning(
                f"Cookie file expiring soon: {status.days_until_expiry} days remaining"
            )

        return status
