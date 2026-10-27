"""Append-only, hash-chained audit trail."""

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from . import policy
from .clock import from_utc_text, to_utc_text, years_before

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    seq INTEGER PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    at TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
"""

INSERT_AUDIT_EVENT = (
    "INSERT INTO audit_events (seq, actor, action, target, at, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?)"
)
SELECT_LAST_AUDIT_EVENT = "SELECT seq, hash FROM audit_events ORDER BY seq DESC LIMIT 1"
SELECT_AUDIT_EVENTS = "SELECT seq, actor, action, target, at, prev_hash, hash FROM audit_events ORDER BY seq"
DELETE_AUDIT_EVENTS_BEFORE = "DELETE FROM audit_events WHERE at < ?"

GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class AuditEvent:
    seq: int
    actor: str
    action: str
    target: str
    at: datetime
    prev_hash: str
    hash: str


def event_hash(prev_hash: str, seq: int, actor: str, action: str, target: str, at_text: str) -> str:
    material = "\n".join([prev_hash, str(seq), actor, action, target, at_text])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._conn.executescript(AUDIT_SCHEMA)

    def record(self, actor: str, action: str, target: str, at: datetime) -> AuditEvent:
        last = self._conn.execute(SELECT_LAST_AUDIT_EVENT).fetchone()
        seq = 1 if last is None else last[0] + 1
        prev_hash = GENESIS_HASH if last is None else last[1]
        at_text = to_utc_text(at)
        digest = event_hash(prev_hash, seq, actor, action, target, at_text)
        self._conn.execute(INSERT_AUDIT_EVENT, (seq, actor, action, target, at_text, prev_hash, digest))
        return AuditEvent(seq, actor, action, target, from_utc_text(at_text), prev_hash, digest)

    def events(self) -> list[AuditEvent]:
        rows = self._conn.execute(SELECT_AUDIT_EVENTS).fetchall()
        return [_event(row) for row in rows]

    def verify(self) -> bool:
        """True when every retained event links to the one before it and its hash matches its content."""
        rows = self._conn.execute(SELECT_AUDIT_EVENTS).fetchall()
        if not rows:
            return True
        expected_seq = rows[0][0]
        expected_prev = rows[0][5]
        for seq, actor, action, target, at_text, prev_hash, digest in rows:
            if seq != expected_seq or prev_hash != expected_prev:
                return False
            if digest != event_hash(prev_hash, seq, actor, action, target, at_text):
                return False
            expected_seq = seq + 1
            expected_prev = digest
        return True

    def purge_expired(self, now: datetime) -> int:
        """Drop events older than the retention period. Returns how many were dropped."""
        cutoff = years_before(now, policy.AUDIT_RETENTION_YEARS)
        cursor = self._conn.execute(DELETE_AUDIT_EVENTS_BEFORE, (to_utc_text(cutoff),))
        return cursor.rowcount


def _event(row: tuple) -> AuditEvent:
    seq, actor, action, target, at_text, prev_hash, digest = row
    return AuditEvent(seq, actor, action, target, from_utc_text(at_text), prev_hash, digest)
