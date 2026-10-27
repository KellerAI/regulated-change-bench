from datetime import date, datetime, timezone
from decimal import Decimal

from payments import reports
from payments.models import Payment


def payment(pid, amount, status="pending", currency="USD"):
    created = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    return Payment(pid, f"INS-{pid}", 1, Decimal(amount), currency, "", status, "clerk.ana", created, ())


def test_day_bounds_are_utc_midnights():
    start, end = reports.day_bounds(date(2026, 9, 1))
    assert start == datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 9, 2, tzinfo=timezone.utc)


def test_daily_totals_by_currency():
    created = [payment(1, "100.00"), payment(2, "250.50")]
    released = [payment(3, "40.00", status="released")]
    [totals] = reports.daily_totals(date(2026, 9, 1), created, released)
    assert totals.currency == "USD"
    assert totals.created_count == 2
    assert totals.created_amount == Decimal("350.50")
    assert totals.released_count == 1
    assert totals.released_amount == Decimal("40.00")


def test_daily_totals_empty_day():
    assert reports.daily_totals(date(2026, 9, 1), [], []) == []


def test_ledger_csv():
    text = reports.ledger_csv([payment(1, "100.00")])
    lines = text.splitlines()
    assert lines[0] == ",".join(reports.LEDGER_COLUMNS)
    assert lines[1].startswith("1,INS-1,1,100.00,USD,pending,clerk.ana,2026-09-01T10:00:00")
