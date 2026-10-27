from decimal import Decimal

import pytest

from payments import payments, policy
from payments.errors import Conflict, DuplicateApprovalError, Forbidden, SelfApprovalError, ValidationError
from support import CORE_BANKING, START, actor


@pytest.fixture
def store(service):
    return service.store


@pytest.fixture
def outbound(service):
    return service.outbound


def new_payment(store, payee, amount="250.00", creator="clerk.ana"):
    payee_record = store.get_payee(payee.id)
    return payments.create(store, actor(creator), payee_record, Decimal(amount), "USD", "Invoice 4471", START)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("12.5", Decimal("12.50")), ("0.01", Decimal("0.01")), (100, Decimal("100.00"))],
)
def test_parse_amount_accepts(text, expected):
    assert payments.parse_amount(text) == expected


@pytest.mark.parametrize("text", ["abc", "0", "-5.00", "1.001", "NaN", "Infinity", "5000000.01"])
def test_parse_amount_rejects(text):
    with pytest.raises(ValidationError):
        payments.parse_amount(text)


def test_required_approvals_around_the_threshold():
    threshold = policy.DUAL_CONTROL_THRESHOLD
    assert payments.required_approvals(threshold - Decimal("0.01")) == 1
    assert payments.required_approvals(threshold) == 2


def test_small_payment_is_approved_by_one_approver(store, payee):
    payment = new_payment(store, payee)
    approved = payments.approve(store, actor("officer.ben"), payment, START)
    assert approved.status == "approved"
    assert approved.approvers == ("officer.ben",)


def test_large_payment_needs_a_second_approver(store, payee):
    payment = new_payment(store, payee, amount="15000.00")
    once = payments.approve(store, actor("officer.ben"), payment, START)
    assert once.status == "pending"
    twice = payments.approve(store, actor("treasury.dee"), once, START)
    assert twice.status == "approved"


def test_creator_cannot_approve(store, payee):
    payment = new_payment(store, payee, creator="officer.ben")
    with pytest.raises(SelfApprovalError):
        payments.approve(store, actor("officer.ben"), payment, START)


def test_same_approver_cannot_approve_twice(store, payee):
    payment = new_payment(store, payee, amount="15000.00")
    once = payments.approve(store, actor("officer.ben"), payment, START)
    with pytest.raises(DuplicateApprovalError):
        payments.approve(store, actor("officer.ben"), once, START)


def test_approved_payment_cannot_be_approved_again(store, payee):
    payment = new_payment(store, payee)
    approved = payments.approve(store, actor("officer.ben"), payment, START)
    with pytest.raises(Conflict):
        payments.approve(store, actor("treasury.dee"), approved, START)


def test_release_needs_approval(store, payee, outbound, transport):
    payment = new_payment(store, payee)
    with pytest.raises(Conflict):
        payments.release(store, actor("treasury.dee"), payment, outbound, START)
    assert transport.sent_to(CORE_BANKING) == []


def test_release_sends_npi_only_to_core_banking(store, payee, outbound, transport):
    payment = payments.approve(store, actor("officer.ben"), new_payment(store, payee), START)
    result = payments.release(store, actor("treasury.dee"), payment, outbound, START)
    assert result.confirmation.startswith("CONF-")
    sent = transport.sent_to(CORE_BANKING)
    assert len(sent) == 1
    assert sent[0]["account_number"] == "880012345678"
    assert store.get_payment(payment.id).status == "released"


def test_release_is_idempotent(store, payee, outbound, transport):
    payment = payments.approve(store, actor("officer.ben"), new_payment(store, payee), START)
    first = payments.release(store, actor("treasury.dee"), payment, outbound, START)
    second = payments.release(store, actor("treasury.dee"), store.get_payment(payment.id), outbound, START)
    assert second == first
    assert len(transport.sent_to(CORE_BANKING)) == 1


def test_release_to_closed_payee_is_refused(store, payee, outbound):
    payment = payments.approve(store, actor("officer.ben"), new_payment(store, payee), START)
    store.close_payee(payee.id, START)
    with pytest.raises(Conflict):
        payments.release(store, actor("treasury.dee"), payment, outbound, START)


def test_missing_confirmation_is_an_integration_error(store, payee, outbound, transport):
    transport.reply(CORE_BANKING, {"status": "queued"})
    payment = payments.approve(store, actor("officer.ben"), new_payment(store, payee), START)
    with pytest.raises(Exception) as caught:
        payments.release(store, actor("treasury.dee"), payment, outbound, START)
    assert caught.value.code == "integration_failed"
    assert store.find_release(payment.instruction_id) is None


def test_create_checks_payee_and_currency(store, payee):
    with pytest.raises(ValidationError):
        payments.create(store, actor("clerk.ana"), store.get_payee(payee.id), Decimal("1.00"), "EUR", "", START)
    store.close_payee(payee.id, START)
    with pytest.raises(ValidationError):
        new_payment(store, payee)


def test_amend_memo_by_creator_while_pending(store, payee):
    payment = new_payment(store, payee)
    amended = payments.amend_memo(store, actor("clerk.ana"), payment, "  Invoice 4472 ")
    assert amended.memo == "Invoice 4472"
    with pytest.raises(Forbidden):
        payments.amend_memo(store, actor("officer.ben"), amended, "Invoice 9")
    approved = payments.approve(store, actor("officer.ben"), amended, START)
    with pytest.raises(Conflict):
        payments.amend_memo(store, actor("clerk.ana"), approved, "late change")
