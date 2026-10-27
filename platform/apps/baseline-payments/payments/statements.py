"""Monthly payee statements: the payments made to one payee in a calendar month."""

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

from . import npi
from .errors import ValidationError
from .models import Payee, Payment

STATEMENT_COLUMNS = ("payment_id", "date", "memo", "amount", "currency", "status")


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    if not 1 <= month <= 12:
        raise ValidationError("month must be between 1 and 12")
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        return start, datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return start, datetime(year, month + 1, 1, tzinfo=timezone.utc)


def parse_period(text: str) -> tuple[int, int]:
    """'2026-09' -> (2026, 9)."""
    try:
        year_text, month_text = text.split("-")
        return int(year_text), int(month_text)
    except ValueError as exc:
        raise ValidationError("period must look like YYYY-MM") from exc


def render(payee: Payee, payments: list[Payment], year: int, month: int) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["statement", f"{year:04d}-{month:02d}"])
    writer.writerow(["payee", payee.holder_name])
    writer.writerow(["account", npi.mask("account_number", payee.account_number)])
    writer.writerow(STATEMENT_COLUMNS)
    for p in payments:
        writer.writerow([p.id, p.created_at.date().isoformat(), p.memo, p.amount, p.currency, p.status])
    total = sum((p.amount for p in payments if p.status == "released"), Decimal("0.00"))
    writer.writerow(["total_released", total])
    return buffer.getvalue()
