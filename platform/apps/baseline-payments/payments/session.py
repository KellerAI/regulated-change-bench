"""Authenticated sessions with idle timeouts."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import policy


def idle_limit(privileged: bool) -> timedelta:
    if privileged:
        return timedelta(minutes=policy.PRIVILEGED_IDLE_MINUTES)
    return timedelta(minutes=policy.STANDARD_IDLE_MINUTES)


@dataclass
class Session:
    token: str
    user_id: str
    role: str
    mfa_verified: bool
    last_seen: datetime

    def is_active(self, now: datetime, privileged: bool) -> bool:
        return now - self.last_seen < idle_limit(privileged)

    def touch(self, now: datetime) -> None:
        self.last_seen = now


def new_token() -> str:
    return secrets.token_urlsafe(24)


class SessionStore:
    """Sessions issued after sign-in. Sign-in itself happens at the bank's identity provider."""

    def __init__(self, clock, token_factory=new_token) -> None:
        self._clock = clock
        self._token_factory = token_factory
        self._sessions: dict[str, Session] = {}

    def open(self, user_id: str, role: str, mfa_verified: bool = False) -> Session:
        token = self._token_factory()
        session = Session(token, user_id, role, mfa_verified, self._clock.now())
        self._sessions[token] = session
        return session

    def get(self, token: str) -> Session | None:
        return self._sessions.get(token)

    def verify_mfa(self, token: str) -> None:
        session = self._sessions[token]
        session.mfa_verified = True

    def close(self, token: str) -> None:
        self._sessions.pop(token, None)
