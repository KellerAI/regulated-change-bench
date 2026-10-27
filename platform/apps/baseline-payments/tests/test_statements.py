from datetime import datetime, timezone
from decimal import Decimal

import pytest

from payments import statements
from payments.errors import ValidationError
from payments.models import Payee, Payment

WHEN = datetime(2026, 9, 3, 10, tzinfo=timezone.utc)


def payee(account_number="880012345678"):
    return Payee(1, "Northwind Office Supply", "vendor", account_number, "990000123", "00-1234567", None,
                 "open", "officer.ben", WHEN, None, False, None)


def payment(pid, amount, status):
    return Payment(pid, f"INS-{pid}", 1, Decimal(amount), "USD", "Invoice 44", status, "clerk.ana", WHEN, ())


def test_month_bounds():
    assert statements.month_bounds(2026, 9) == (
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    assert statements.month_bounds(2026, 12)[1] == datetime(2027, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        statements.month_bounds(2026, 13)


def test_parse_period():
    assert statements.parse_period("2026-09") == (2026, 9)
    with pytest.raises(ValidationError):
        statements.parse_period("September")


def test_render_masks_the_account_and_totals_released():
    text = statements.render(payee(), [payment(1, "100.00", "released"), payment(2, "5.00", "pending")], 2026, 9)
    assert "880012345678" not in text
    assert "account,****5678" in text
    assert text.splitlines()[-1] == "total_released,100.00"


def test_render_after_purge():
    text = statements.render(payee(account_number=None), [], 2026, 9)
    assert "account,\n" in text
