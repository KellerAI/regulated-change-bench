"""Shared values and builders for the unit tests."""

from datetime import datetime, timezone
from pathlib import Path

from payments.models import Actor, PayeeDetails

START = datetime(2026, 9, 1, 13, 0, tzinfo=timezone.utc)

USERS = {
    "clerk.ana": "clerk",
    "officer.ben": "payments_officer",
    "officer.cai": "payments_officer",
    "treasury.dee": "treasury_manager",
    "treasury.eli": "treasury_manager",
    "auditor.fay": "auditor",
    "admin.gus": "it_admin",
}

CORE_BANKING = "https://core.fernbrook.example/api/disbursements"
SCREENING = "https://screening.fernbrook.example/v1/screen"
STATEMENTS = "https://statements.fernbrook.example/v1/statements"


def details(**overrides) -> PayeeDetails:
    values = {
        "holder_name": "Northwind Office Supply",
        "category": "vendor",
        "account_number": "880012345678",
        "routing_number": "990000123",
        "tax_id": "00-1234567",
        "date_of_birth": None,
    }
    values.update(overrides)
    return PayeeDetails(**values)


def actor(user_id: str) -> Actor:
    return Actor(user_id, USERS[user_id])


def platform_root() -> Path:
    """The platform tree that holds this app and its controls/ directory."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "controls" / "payments").is_dir():
            return candidate
    raise RuntimeError("controls/payments not found above the app")
