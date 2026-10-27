from datetime import datetime, timezone

import pytest

from payments.clock import FixedClock, from_utc_text, months_before, to_utc_text, years_before


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_fixed_clock_moves_only_when_told():
    clock = FixedClock(utc(2026, 9, 1, 12))
    assert clock.now() == utc(2026, 9, 1, 12)
    clock.advance(minutes=5)
    assert clock.now() == utc(2026, 9, 1, 12, 5)
    clock.set(utc(2027, 1, 1))
    assert clock.now() == utc(2027, 1, 1)


def test_fixed_clock_rejects_naive_times():
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 9, 1))


@pytest.mark.parametrize(
    ("moment", "months", "expected"),
    [
        (utc(2026, 9, 15), 1, utc(2026, 8, 15)),
        (utc(2026, 3, 31), 1, utc(2026, 2, 28)),
        (utc(2026, 1, 10), 1, utc(2025, 12, 10)),
        (utc(2026, 9, 1), 84, utc(2019, 9, 1)),
    ],
)
def test_months_before(moment, months, expected):
    assert months_before(moment, months) == expected


def test_years_before_handles_leap_day():
    assert years_before(utc(2028, 2, 29), 1) == utc(2027, 2, 28)


def test_utc_text_round_trips_and_sorts():
    early = to_utc_text(utc(2026, 9, 1, 9, 0, 0))
    late = to_utc_text(datetime(2026, 9, 1, 9, 0, 0, 500000, tzinfo=timezone.utc))
    assert early < late
    assert from_utc_text(early) == utc(2026, 9, 1, 9)
    assert from_utc_text(None) is None
