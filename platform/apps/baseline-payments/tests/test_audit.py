from datetime import datetime, timedelta, timezone

import sqlite3

from payments import policy
from payments.audit import GENESIS_HASH, AuditLog
from payments.clock import years_before

NOW = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def new_log():
    connection = sqlite3.connect(":memory:", isolation_level=None)
    return connection, AuditLog(connection)


def test_events_are_chained():
    connection, log = new_log()
    first = log.record("clerk.ana", "create_payment", "payment:1", NOW)
    second = log.record("officer.ben", "approve_payment", "payment:1", NOW)
    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.hash
    assert [e.seq for e in log.events()] == [1, 2]
    assert log.verify()


def test_edited_event_breaks_the_chain():
    connection, log = new_log()
    log.record("clerk.ana", "create_payment", "payment:1", NOW)
    log.record("officer.ben", "approve_payment", "payment:1", NOW)
    connection.execute("UPDATE audit_events SET actor = 'someone.else' WHERE seq = 1")
    assert not log.verify()


def test_removed_event_breaks_the_chain():
    connection, log = new_log()
    for n in range(3):
        log.record("clerk.ana", "create_payment", f"payment:{n}", NOW)
    connection.execute("DELETE FROM audit_events WHERE seq = 2")
    assert not log.verify()


def test_purge_keeps_the_retention_period():
    connection, log = new_log()
    cutoff = years_before(NOW, policy.AUDIT_RETENTION_YEARS)
    log.record("a", "x", "t", cutoff - timedelta(days=1))
    log.record("a", "x", "t", cutoff)
    log.record("a", "x", "t", NOW)
    assert log.purge_expired(NOW) == 1
    assert len(log.events()) == 2
    assert log.verify()


def test_empty_log_verifies():
    assert new_log()[1].verify()
