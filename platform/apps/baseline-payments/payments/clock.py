"""Clocks and calendar arithmetic.

Code takes a clock instead of reading the system time, so that behaviour that
depends on time can be exercised at any moment.
"""

import calendar
from datetime import datetime, timedelta, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """A clock that only moves when told to."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("start must be timezone-aware")
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> datetime:
        self._now = self._now + timedelta(**delta)
        return self._now

    def set(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("moment must be timezone-aware")
        self._now = moment


def months_before(moment: datetime, months: int) -> datetime:
    """The same day-of-month `months` earlier, clamped to the end of shorter months."""
    index = moment.year * 12 + (moment.month - 1) - months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def years_before(moment: datetime, years: int) -> datetime:
    return months_before(moment, years * 12)


def to_utc_text(moment: datetime) -> str:
    """Fixed-width ISO text, so stored timestamps sort chronologically."""
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def from_utc_text(text: str | None) -> datetime | None:
    if text is None:
        return None
    return datetime.fromisoformat(text)
