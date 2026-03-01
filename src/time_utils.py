"""Time utilities for consistent time handling."""

from datetime import datetime, timezone, timedelta


class TimeUtils:
    """Utilities for time handling."""

    BEIJING_TZ = timezone(timedelta(hours=8))

    @staticmethod
    def now_utc() -> datetime:
        """Get current UTC time."""
        return datetime.now(timezone.utc)

    @classmethod
    def to_beijing(cls, dt: datetime) -> datetime:
        """Convert datetime to Beijing timezone."""
        return dt.astimezone(cls.BEIJING_TZ)

    @classmethod
    def beijing_now_str(cls) -> str:
        """Get current Beijing time as formatted string."""
        beijing_time = cls.to_beijing(cls.now_utc())
        return beijing_time.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def ensure_utc(dt: datetime) -> datetime:
        """Ensure datetime has UTC timezone."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def parse_datetime(dt_str: str) -> datetime:
        """Parse datetime string and ensure UTC timezone."""
        dt = datetime.fromisoformat(dt_str)
        return TimeUtils.ensure_utc(dt)

    @staticmethod
    def hours_since(dt: datetime) -> float:
        """Calculate hours since given datetime."""
        now = TimeUtils.now_utc()
        dt = TimeUtils.ensure_utc(dt)
        time_diff = now - dt
        return time_diff.total_seconds() / 3600
