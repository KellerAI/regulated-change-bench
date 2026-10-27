import pytest

from payments import directory
from payments.errors import ValidationError
from payments.store import Store
from payments.vault import Vault
from support import START, details


def test_validate_trims_the_name():
    clean = directory.validate(details(holder_name="  Northwind   Office Supply "))
    assert clean.holder_name == "Northwind Office Supply"


@pytest.mark.parametrize(
    "overrides",
    [
        {"holder_name": "   "},
        {"category": "friend"},
        {"account_number": "12345"},
        {"account_number": "12345x789"},
        {"routing_number": "12345678"},
        {"tax_id": "123456789"},
        {"date_of_birth": "14/03/1975"},
    ],
)
def test_validate_rejects_bad_input(overrides):
    with pytest.raises(ValidationError):
        directory.validate(details(**overrides))


def test_validation_messages_do_not_echo_values():
    with pytest.raises(ValidationError) as caught:
        directory.validate(details(account_number="12345"))
    assert "12345" not in str(caught.value)


def test_summary_masks_the_account_number():
    store = Store(Vault())
    payee = store.add_payee(details(), "officer.ben", START)
    summary = directory.summarize(payee)
    assert summary.account_number == "****5678"
    assert summary.status == "open"
    assert not summary.legal_hold


def test_search_by_prefix_escapes_wildcards():
    store = Store(Vault())
    store.add_payee(details(holder_name="Northwind Office Supply"), "officer.ben", START)
    store.add_payee(details(holder_name="North_Star Freight"), "officer.ben", START)
    store.add_payee(details(holder_name="Harbor Water Utility"), "officer.ben", START)
    assert [s.holder_name for s in directory.search(store, "north")] == [
        "North_Star Freight",
        "Northwind Office Supply",
    ]
    assert [s.holder_name for s in directory.search(store, "North_")] == ["North_Star Freight"]
    assert directory.search(store, "%") == []


def test_like_prefix():
    assert directory.like_prefix(" 50%_off ") == "50\\%\\_off%"
