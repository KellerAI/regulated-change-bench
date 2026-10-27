"""Fixtures for the tests in this directory.

Approved values are read from `controls/payments/` in the platform tree,
found by walking up from this file.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from payments.app import LedgerApp
from payments.client import WsgiClient
from payments.clock import FixedClock
from payments.models import Actor, PayeeDetails
from payments.service import LedgerService, build_service
from payments.session import SessionStore
from payments.transports import RecordingTransport

APP = "payments"
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

NPI_SAMPLE = {
    "account_number": "880012345678",
    "routing_number": "990000123",
    "tax_id": "000-12-3456",
    "date_of_birth": "1975-03-14",
}


def find_platform_root(start: Path) -> Path:
    for candidate in start.parents:
        if (candidate / "controls" / APP).is_dir():
            return candidate
    raise RuntimeError(f"no controls/{APP} directory above {start}")


@pytest.fixture(scope="session")
def platform_root() -> Path:
    return find_platform_root(Path(__file__).resolve())


def _load(root: Path, name: str) -> dict:
    return json.loads((root / "controls" / APP / name).read_text())


@pytest.fixture(scope="session")
def access_policy(platform_root) -> dict:
    return _load(platform_root, "access-policy.json")


@pytest.fixture(scope="session")
def policy_params(platform_root) -> dict:
    return _load(platform_root, "policy-params.json")


@pytest.fixture(scope="session")
def asset_inventory(platform_root) -> dict:
    return _load(platform_root, "asset-inventory.json")


@dataclass
class Platform:
    """A wired service and HTTP app on a fixed clock with an in-process transport."""

    service: LedgerService
    clock: FixedClock
    transport: RecordingTransport
    sessions: SessionStore
    client: WsgiClient

    def actor(self, user_id: str) -> Actor:
        return Actor(user_id, USERS[user_id])

    def token(self, user_id: str, role: str | None = None, mfa: bool = True) -> str:
        return self.sessions.open(user_id, role or USERS[user_id], mfa_verified=mfa).token

    def add_payee(self, holder_name: str = "Harbor Freight Lines", **overrides: str) -> int:
        values = dict(NPI_SAMPLE)
        values.update(overrides)
        details = PayeeDetails(holder_name=holder_name, category="vendor", **values)
        return self.service.add_payee(self.actor("officer.ben"), details).id

    def approve_as_required(self, payment_id: int, approvers=("officer.ben", "treasury.eli")) -> None:
        """Collect approvals until the payment is approved."""
        for user_id in approvers:
            if self.service.store.get_payment(payment_id).status != "pending":
                return
            self.service.approve_payment(self.actor(user_id), payment_id)


@pytest.fixture
def npi_sample() -> dict:
    return dict(NPI_SAMPLE)


@pytest.fixture
def platform() -> Platform:
    clock = FixedClock(START)
    transport = RecordingTransport()
    service = build_service(clock, transport)
    for user_id, role in USERS.items():
        service.store.add_user(user_id, role)
    sessions = SessionStore(clock)
    client = WsgiClient(LedgerApp(service, sessions, clock))
    return Platform(service, clock, transport, sessions, client)
