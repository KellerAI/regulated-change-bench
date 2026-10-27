from datetime import timedelta

from payments import policy, retention
from payments.clock import months_before
from support import START, details


def closed_payee(store, closed_at, name="Old Vendor", hold=False):
    payee = store.add_payee(details(holder_name=name), "officer.ben", START)
    store.close_payee(payee.id, closed_at)
    if hold:
        store.set_legal_hold(payee.id, True)
    return payee


def test_purges_only_payees_past_retention(service):
    store = service.store
    cutoff = months_before(START, policy.CLOSED_ACCOUNT_NPI_RETENTION_MONTHS)
    due = closed_payee(store, cutoff - timedelta(days=1))
    not_due = closed_payee(store, cutoff + timedelta(days=1))
    assert retention.purge_due(store, START) == [due.id]
    assert store.get_payee(due.id).account_number is None
    assert store.get_payee(not_due.id).account_number == "880012345678"


def test_open_payees_are_never_purged(service):
    store = service.store
    payee = store.add_payee(details(), "officer.ben", START - timedelta(days=4000))
    assert retention.purge_due(store, START) == []
    assert store.get_payee(payee.id).account_number == "880012345678"


def test_purge_is_not_repeated(service):
    store = service.store
    closed_payee(store, START - timedelta(days=4000))
    assert len(retention.purge_due(store, START)) == 1
    assert retention.purge_due(store, START) == []
