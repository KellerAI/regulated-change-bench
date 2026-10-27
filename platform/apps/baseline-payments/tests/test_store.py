from datetime import timedelta
from decimal import Decimal

import pytest

from payments.errors import Conflict, NotFound
from payments.models import Release
from payments.store import Store
from payments.vault import Vault, is_sealed
from support import START, details


@pytest.fixture
def vault():
    return Vault()


@pytest.fixture
def store(vault):
    return Store(vault)


def test_payee_round_trip(store):
    payee = store.add_payee(details(date_of_birth="1975-03-14"), "officer.ben", START)
    loaded = store.get_payee(payee.id)
    assert loaded.account_number == "880012345678"
    assert loaded.routing_number == "990000123"
    assert loaded.tax_id == "00-1234567"
    assert loaded.date_of_birth == "1975-03-14"
    assert loaded.status == "open"
    assert loaded.created_at == START


def test_npi_columns_are_sealed(store):
    payee = store.add_payee(details(), "officer.ben", START)
    row = store.connection.execute("SELECT account_number, tax_id FROM payees WHERE id = ?", (payee.id,)).fetchone()
    assert is_sealed(row["account_number"])
    assert is_sealed(row["tax_id"])


def test_missing_records_raise_not_found(store):
    with pytest.raises(NotFound):
        store.get_payee(99)
    with pytest.raises(NotFound):
        store.get_payment(99)
    with pytest.raises(NotFound):
        store.get_user("nobody")


def test_users(store):
    user = store.add_user("clerk.ana", "clerk")
    assert user.role == "clerk"
    assert user.active


def test_payment_ids_and_instruction_ids(store):
    payee = store.add_payee(details(), "officer.ben", START)
    first = store.add_payment(payee.id, Decimal("10.00"), "USD", "", "clerk.ana", START)
    second = store.add_payment(payee.id, Decimal("20.00"), "USD", "", "clerk.ana", START, "INS-EXTERNAL-7")
    assert (first.id, second.id) == (1, 2)
    assert first.instruction_id == "INS-00000001"
    assert second.instruction_id == "INS-EXTERNAL-7"
    assert first.amount == Decimal("10.00")


def test_duplicate_instruction_is_a_conflict(store):
    payee = store.add_payee(details(), "officer.ben", START)
    store.add_payment(payee.id, Decimal("10.00"), "USD", "", "clerk.ana", START, "INS-A")
    with pytest.raises(Conflict):
        store.add_payment(payee.id, Decimal("10.00"), "USD", "", "clerk.ana", START, "INS-A")


def test_approvals_keep_their_order(store):
    payee = store.add_payee(details(), "officer.ben", START)
    payment = store.add_payment(payee.id, Decimal("10.00"), "USD", "", "clerk.ana", START)
    store.add_approval(payment.id, "officer.ben", START)
    store.add_approval(payment.id, "treasury.dee", START)
    assert store.get_payment(payment.id).approvers == ("officer.ben", "treasury.dee")


def test_release_lookup_returns_the_first(store):
    payee = store.add_payee(details(), "officer.ben", START)
    payment = store.add_payment(payee.id, Decimal("10.00"), "USD", "", "clerk.ana", START)
    first = Release(payment.instruction_id, payment.id, "treasury.dee", START, "CONF-1")
    store.add_release(first)
    assert store.find_release(payment.instruction_id) == first
    assert store.find_release("INS-UNKNOWN") is None


def test_time_window_queries(store):
    payee = store.add_payee(details(), "officer.ben", START)
    store.add_payment(payee.id, Decimal("1.00"), "USD", "", "clerk.ana", START)
    store.add_payment(payee.id, Decimal("2.00"), "USD", "", "clerk.ana", START + timedelta(days=1))
    window = store.payments_created_between(START, START + timedelta(hours=1))
    assert [p.amount for p in window] == [Decimal("1.00")]
    for_payee = store.payments_for_payee_between(payee.id, START, START + timedelta(days=2))
    assert len(for_payee) == 2


def test_purge_clears_npi(store):
    payee = store.add_payee(details(date_of_birth="1975-03-14"), "officer.ben", START)
    store.purge_payee_npi(payee.id, START)
    purged = store.get_payee(payee.id)
    assert purged.account_number is None
    assert purged.date_of_birth is None
    assert purged.npi_purged_at == START
    assert purged.holder_name == "Northwind Office Supply"


def test_reseal_uses_the_active_key(store, vault):
    payee = store.add_payee(details(), "officer.ben", START)
    vault.rotate()
    store.reseal_payee(payee.id)
    row = store.connection.execute("SELECT account_number FROM payees WHERE id = ?", (payee.id,)).fetchone()
    assert vault.version_of(row["account_number"]) == 2
    assert store.get_payee(payee.id).account_number == "880012345678"


def test_closed_payees_before_cutoff(store):
    old = store.add_payee(details(holder_name="Old Co"), "officer.ben", START)
    recent = store.add_payee(details(holder_name="Recent Co"), "officer.ben", START)
    store.close_payee(old.id, START - timedelta(days=400))
    store.close_payee(recent.id, START)
    found = store.closed_payees_before(START - timedelta(days=30))
    assert [p.id for p in found] == [old.id]
