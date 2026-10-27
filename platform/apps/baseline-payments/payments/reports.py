"""Operational reports: daily totals and the ledger export."""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from .models import Payment

LEDGER_COLUMNS = (
    "payment_id",
    "instruction_id",
    "payee_id",
    "amount",
    "currency",
    "status",
    "created_by",
    "created_at",
)


@dataclass(frozen=True)
class DailyTotals:
    day: date
    currency: str
    created_count: int
    created_amount: Decimal
    released_count: int
    released_amount: Decimal


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def daily_totals(day: date, created: list[Payment], released: list[Payment]) -> list[DailyTotals]:
    """Totals per currency for payments created and payments released on `day`."""
    currencies = sorted({p.currency for p in created} | {p.currency for p in released})
    return [_totals_for(day, currency, created, released) for currency in currencies]


def _totals_for(day: date, currency: str, created: list[Payment], released: list[Payment]) -> DailyTotals:
    created_here = [p for p in created if p.currency == currency]
    released_here = [p for p in released if p.currency == currency]
    return DailyTotals(
        day=day,
        currency=currency,
        created_count=len(created_here),
        created_amount=sum((p.amount for p in created_here), Decimal("0.00")),
        released_count=len(released_here),
        released_amount=sum((p.amount for p in released_here), Decimal("0.00")),
    )


def ledger_csv(payments: list[Payment]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(LEDGER_COLUMNS)
    for p in payments:
        writer.writerow(_ledger_row(p))
    return buffer.getvalue()


def _ledger_row(p: Payment) -> list:
    return [
        p.id,
        p.instruction_id,
        p.payee_id,
        p.amount,
        p.currency,
        p.status,
        p.created_by,
        p.created_at.isoformat(),
    ]
