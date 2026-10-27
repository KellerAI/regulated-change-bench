import pytest

from payments.app import LedgerApp
from payments.client import WsgiClient
from payments.clock import FixedClock
from payments.service import build_service
from payments.session import SessionStore
from payments.transports import RecordingTransport
from support import START, USERS, actor, details


@pytest.fixture
def clock():
    return FixedClock(START)


@pytest.fixture
def transport():
    return RecordingTransport()


@pytest.fixture
def service(clock, transport):
    svc = build_service(clock, transport)
    for user_id, role in USERS.items():
        svc.store.add_user(user_id, role)
    return svc


@pytest.fixture
def payee(service):
    return service.add_payee(actor("officer.ben"), details())


@pytest.fixture
def sessions(clock):
    return SessionStore(clock)


@pytest.fixture
def client(service, sessions, clock):
    return WsgiClient(LedgerApp(service, sessions, clock))


@pytest.fixture
def login(sessions):
    def open_session(user_id: str, mfa: bool = True) -> str:
        return sessions.open(user_id, USERS[user_id], mfa_verified=mfa).token

    return open_session
