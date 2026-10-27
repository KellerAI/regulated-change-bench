from datetime import timedelta

from payments import policy
from payments.session import SessionStore, idle_limit


def test_idle_limits_follow_policy():
    assert idle_limit(True) == timedelta(minutes=policy.PRIVILEGED_IDLE_MINUTES)
    assert idle_limit(False) == timedelta(minutes=policy.STANDARD_IDLE_MINUTES)
    assert idle_limit(True) < idle_limit(False)


def test_session_expires_after_privileged_idle_limit(clock):
    store = SessionStore(clock)
    session = store.open("treasury.dee", "treasury_manager", mfa_verified=True)
    clock.advance(minutes=policy.PRIVILEGED_IDLE_MINUTES - 1)
    assert session.is_active(clock.now(), privileged=True)
    clock.advance(minutes=1)
    assert not session.is_active(clock.now(), privileged=True)
    assert session.is_active(clock.now(), privileged=False)


def test_touch_resets_idle_time(clock):
    store = SessionStore(clock)
    session = store.open("clerk.ana", "clerk")
    clock.advance(minutes=20)
    session.touch(clock.now())
    clock.advance(minutes=20)
    assert session.is_active(clock.now(), privileged=False)


def test_store_open_get_verify_close(clock):
    tokens = iter(["t-1", "t-2"])
    store = SessionStore(clock, token_factory=lambda: next(tokens))
    session = store.open("clerk.ana", "clerk")
    assert session.token == "t-1"
    assert store.get("t-1") is session
    assert not session.mfa_verified
    store.verify_mfa("t-1")
    assert session.mfa_verified
    store.close("t-1")
    assert store.get("t-1") is None


def test_default_tokens_are_distinct(clock):
    store = SessionStore(clock)
    first = store.open("clerk.ana", "clerk")
    second = store.open("clerk.ana", "clerk")
    assert first.token != second.token
