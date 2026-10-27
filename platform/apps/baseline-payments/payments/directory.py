"""Payee directory: validating new payees and listing them with NPI masked."""

import re
from dataclasses import dataclass, replace
from datetime import date

from . import npi
from .errors import ValidationError
from .models import Payee, PayeeDetails

PAYEE_CATEGORIES = ("vendor", "customer", "employee", "tax_authority")
NAME_MAX_LENGTH = 80
_ACCOUNT_NUMBER = re.compile(r"\d{6,17}")
_ROUTING_NUMBER = re.compile(r"\d{9}")
_TAX_ID = re.compile(r"\d{3}-\d{2}-\d{4}|\d{2}-\d{7}")


@dataclass(frozen=True)
class PayeeSummary:
    id: int
    holder_name: str
    category: str
    account_number: str
    status: str
    legal_hold: bool


def validate(details: PayeeDetails) -> PayeeDetails:
    name = " ".join(details.holder_name.split())
    if not name or len(name) > NAME_MAX_LENGTH:
        raise ValidationError(f"holder name must be 1 to {NAME_MAX_LENGTH} characters")
    if details.category not in PAYEE_CATEGORIES:
        raise ValidationError(f"category must be one of {', '.join(PAYEE_CATEGORIES)}")
    if not _ACCOUNT_NUMBER.fullmatch(details.account_number or ""):
        raise ValidationError("account number must be 6 to 17 digits")
    if not _ROUTING_NUMBER.fullmatch(details.routing_number or ""):
        raise ValidationError("routing number must be 9 digits")
    if not _TAX_ID.fullmatch(details.tax_id or ""):
        raise ValidationError("tax id must look like 123-45-6789 or 12-3456789")
    if details.date_of_birth is not None:
        _check_date(details.date_of_birth)
    return replace(details, holder_name=name)


def _check_date(text: str) -> None:
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError("date of birth must be YYYY-MM-DD") from exc


def summarize(payee: Payee) -> PayeeSummary:
    return PayeeSummary(
        id=payee.id,
        holder_name=payee.holder_name,
        category=payee.category,
        account_number=npi.mask("account_number", payee.account_number),
        status=payee.status,
        legal_hold=payee.legal_hold,
    )


def like_prefix(prefix: str) -> str:
    """A LIKE pattern matching names that start with `prefix`, with wildcards escaped."""
    escaped = prefix.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped + "%"


def search(store, prefix: str) -> list[PayeeSummary]:
    return [summarize(payee) for payee in store.find_payees_by_name(like_prefix(prefix))]
