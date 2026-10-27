import ast
import re
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

import payments
from payments import audit, policy
from payments.audit import AuditLog
from payments.clock import years_before

AUDIT_MUTATION = re.compile(
    r"\b(update|delete\s+from|replace\s+into|insert\s+or\s+replace\s+into|drop\s+table|alter\s+table)\s+audit_events\b",
    re.IGNORECASE,
)


def expect_event(log, after_seq, actor, action, target, at):
    new = [event for event in log.events() if event.seq > after_seq]
    assert [(e.actor, e.action, e.target, e.at) for e in new] == [(actor, action, target, at)]
    return new[0].seq


@pytest.mark.control(obligation="AUD-1", coverage="sample", domain="payments.sampled_operations")
def test_sampled_operations_are_audited(platform):
    service = platform.service
    log = service.audit_log
    payee_id = platform.add_payee()
    seq = log.events()[-1].seq
    platform.clock.advance(minutes=1)
    payment = service.create_payment(platform.actor("clerk.ana"), payee_id, "2500.00", memo="Invoice 9")
    target = f"payment:{payment.id}"
    seq = expect_event(log, seq, "clerk.ana", "create_payment", target, platform.clock.now())
    platform.clock.advance(minutes=1)
    service.approve_payment(platform.actor("officer.ben"), payment.id)
    seq = expect_event(log, seq, "officer.ben", "approve_payment", target, platform.clock.now())
    platform.clock.advance(minutes=1)
    service.release_payment(platform.actor("treasury.dee"), payment.id)
    expect_event(log, seq, "treasury.dee", "release_payment", target, platform.clock.now())


def generated_log(start, count):
    connection = sqlite3.connect(":memory:", isolation_level=None)
    log = AuditLog(connection)
    actions = ("create_payment", "approve_payment", "release_payment")
    for n in range(count):
        log.record(f"user.{n % 5}", actions[n % 3], f"payment:{n}", start + timedelta(minutes=n))
    return connection, log


def assert_chain_detects_edits(connection, log):
    assert log.verify()
    events = log.events()
    for event in events:
        for column in ("actor", "action", "target", "at", "prev_hash", "hash"):
            connection.execute("SAVEPOINT probe")
            connection.execute(f"UPDATE audit_events SET {column} = 'x' WHERE seq = ?", (event.seq,))
            assert not log.verify(), (event.seq, column)
            connection.execute("ROLLBACK TO probe")
            connection.execute("RELEASE probe")
    for event in events[1:-1]:
        connection.execute("SAVEPOINT probe")
        connection.execute("DELETE FROM audit_events WHERE seq = ?", (event.seq,))
        assert not log.verify(), event.seq
        connection.execute("ROLLBACK TO probe")
        connection.execute("RELEASE probe")
    assert log.verify()


def audit_statements_in_package():
    found = []
    for path in sorted(Path(payments.__file__).parent.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and AUDIT_MUTATION.search(node.value):
                found.append(node.value)
    return found


@pytest.mark.control(obligation="AUD-2", coverage="exhaustive", domain="payments.audit_trail")
def test_chain_and_retention(policy_params, platform):
    approved_years = policy_params["payments.audit_retention_years"]
    assert approved_years >= policy_params["payments.audit_retention_years_rule_minimum"]
    assert policy.AUDIT_RETENTION_YEARS == approved_years
    now = platform.clock.now()
    connection, log = generated_log(now, 30)
    assert_chain_detects_edits(connection, log)
    cutoff = years_before(now, approved_years)
    connection, log = generated_log(now, 0)
    ages = [timedelta(days=d) for d in range(0, 366 * (approved_years + 2), 30)]
    moments = [now - age for age in ages] + [cutoff - timedelta(seconds=1), cutoff, cutoff + timedelta(seconds=1)]
    for moment in sorted(moments):
        log.record("user.1", "create_payment", "payment:1", moment)
    log.purge_expired(now)
    kept = [event.at for event in log.events()]
    assert kept == sorted(m for m in moments if m >= cutoff)
    assert log.verify()
    assert audit.DELETE_AUDIT_EVENTS_BEFORE == "DELETE FROM audit_events WHERE at < ?"
    assert audit_statements_in_package() == [audit.DELETE_AUDIT_EVENTS_BEFORE]
