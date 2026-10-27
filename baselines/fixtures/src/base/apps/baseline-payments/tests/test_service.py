import pytest

from payments.service import Denied, PaymentService


def clock():
    return "2026-01-01T00:00:00Z"


def test_create_and_approve():
    s = PaymentService(clock)
    s.create_payment({"id": "c1", "role": "clerk"}, "p1", "250.00")
    p = s.approve_payment({"id": "o1", "role": "payments_officer"}, "p1")
    assert p["state"] == "approved"


def test_creator_cannot_approve():
    s = PaymentService(clock)
    s.create_payment({"id": "c1", "role": "clerk"}, "p1", "250.00")
    with pytest.raises(Denied):
        s.approve_payment({"id": "c1", "role": "payments_officer"}, "p1")
