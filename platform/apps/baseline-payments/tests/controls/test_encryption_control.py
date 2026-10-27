import pytest

from payments import npi
from payments.vault import is_sealed

SAMPLE = {
    "account_number": "770044190012",
    "routing_number": "990044191",
    "tax_id": "000-44-1923",
    "date_of_birth": "1971-11-23",
}


@pytest.mark.control(obligation="ENC-1", coverage="exhaustive", domain="payments.npi_registry")
def test_every_npi_field_is_sealed_at_rest(policy_params, platform):
    approved = set(policy_params["payments.npi_fields"])
    assert approved <= set(npi.NPI_FIELDS)
    fields = sorted(approved | set(npi.NPI_FIELDS))
    values = {field: SAMPLE.get(field, f"sample-{field}-4419") for field in fields}
    payee_id = platform.add_payee(**values)
    store = platform.service.store
    dump = "\n".join(store.connection.iterdump())
    stored = store.get_payee(payee_id)
    raw = store.connection.execute("SELECT * FROM payees WHERE id = ?", (payee_id,)).fetchone()
    for field in fields:
        assert values[field] not in dump, field
        assert is_sealed(raw[field]), field
        assert getattr(stored, field) == values[field], field
