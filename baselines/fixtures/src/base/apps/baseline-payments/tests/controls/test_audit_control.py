import pytest

from payments.service import PaymentService


@pytest.mark.control(obligation="AUD-1", coverage="sample", domain="payments.operations: create, approve")
def test_sampled_operations_are_audited():
    s = PaymentService(lambda: "2026-01-01T00:00:00Z")
    s.create_payment({"id": "c1", "role": "clerk"}, "p1", "10.00")
    s.approve_payment({"id": "o1", "role": "payments_officer"}, "p1")
    assert [e["action"] for e in s.audit.events] == ["create_payment", "approve_payment"]
