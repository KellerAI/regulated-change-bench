"""Records the service works with."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Actor:
    """Who is making a request: an authenticated user acting in one role."""

    user_id: str
    role: str


@dataclass(frozen=True)
class User:
    user_id: str
    role: str
    active: bool


@dataclass(frozen=True)
class PayeeDetails:
    """What a caller supplies to add a payee to the directory."""

    holder_name: str
    category: str
    account_number: str
    routing_number: str
    tax_id: str
    date_of_birth: str | None = None


@dataclass(frozen=True)
class Payee:
    id: int
    holder_name: str
    category: str
    account_number: str | None
    routing_number: str | None
    tax_id: str | None
    date_of_birth: str | None
    status: str
    created_by: str
    created_at: datetime
    closed_at: datetime | None
    legal_hold: bool
    npi_purged_at: datetime | None


@dataclass(frozen=True)
class Payment:
    id: int
    instruction_id: str
    payee_id: int
    amount: Decimal
    currency: str
    memo: str
    status: str
    created_by: str
    created_at: datetime
    approvers: tuple[str, ...]


@dataclass(frozen=True)
class Release:
    instruction_id: str
    payment_id: int
    released_by: str
    released_at: datetime
    confirmation: str
