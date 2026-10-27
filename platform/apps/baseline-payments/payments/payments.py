"""Payment lifecycle: create, approve, release."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from . import memos, policy
from .errors import (
    Conflict,
    DuplicateApprovalError,
    Forbidden,
    IntegrationError,
    SelfApprovalError,
    ValidationError,
)
from .integrations import OutboundClient
from .models import Actor, Payee, Payment, Release

SUPPORTED_CURRENCIES = frozenset({"USD"})
MAX_PAYMENT_AMOUNT = Decimal("5000000.00")
CENT = Decimal("0.01")


def parse_amount(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError("amount must be a number") from exc
    if not amount.is_finite():
        raise ValidationError("amount must be a number")
    if amount != amount.quantize(CENT):
        raise ValidationError("amount has more than two decimal places")
    if amount <= 0:
        raise ValidationError("amount must be positive")
    if amount > MAX_PAYMENT_AMOUNT:
        raise ValidationError(f"amount exceeds the single-payment maximum of {MAX_PAYMENT_AMOUNT}")
    return amount.quantize(CENT)


def required_approvals(amount: Decimal) -> int:
    if amount >= policy.DUAL_CONTROL_THRESHOLD:
        return 2
    return 1


def is_fully_approved(payment: Payment) -> bool:
    return len(set(payment.approvers)) >= required_approvals(payment.amount)


def create(
    store,
    actor: Actor,
    payee: Payee,
    amount: Decimal,
    currency: str,
    memo: str,
    now: datetime,
    instruction_id: str | None = None,
) -> Payment:
    if payee.status != "open":
        raise ValidationError("payee account is closed")
    if currency not in SUPPORTED_CURRENCIES:
        raise ValidationError(f"currency {currency} is not supported")
    clean_memo = memos.normalize(memo)
    return store.add_payment(payee.id, amount, currency, clean_memo, actor.user_id, now, instruction_id)


def amend_memo(store, actor: Actor, payment: Payment, memo: str) -> Payment:
    if payment.status != "pending":
        raise Conflict("only pending payments can be amended")
    if actor.user_id != payment.created_by:
        raise Forbidden("only the creator of a payment can amend its memo")
    store.set_payment_memo(payment.id, memos.normalize(memo))
    return store.get_payment(payment.id)


def approve(store, actor: Actor, payment: Payment, now: datetime) -> Payment:
    if payment.status != "pending":
        raise Conflict("payment is not awaiting approval")
    if actor.user_id == payment.created_by:
        raise SelfApprovalError("the creator of a payment cannot approve it")
    if actor.user_id in payment.approvers:
        raise DuplicateApprovalError("this approver has already approved the payment")
    store.add_approval(payment.id, actor.user_id, now)
    updated = store.get_payment(payment.id)
    if is_fully_approved(updated):
        store.set_payment_status(payment.id, "approved")
        updated = store.get_payment(payment.id)
    return updated


def release(store, actor: Actor, payment: Payment, outbound: OutboundClient, now: datetime) -> Release:
    """Send an approved payment to core banking. Releasing the same instruction again returns the first release."""
    previous = store.find_release(payment.instruction_id)
    if previous is not None:
        return previous
    if not is_fully_approved(payment):
        raise Conflict("payment does not have the required approvals")
    payee = store.get_payee(payment.payee_id)
    if payee.status != "open":
        raise Conflict("payee account is closed")
    confirmation = _send_disbursement(outbound, payment, payee)
    result = Release(payment.instruction_id, payment.id, actor.user_id, now, confirmation)
    store.add_release(result)
    store.set_payment_status(payment.id, "released")
    return result


def _send_disbursement(outbound: OutboundClient, payment: Payment, payee: Payee) -> str:
    payload = {
        "instruction_id": payment.instruction_id,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "beneficiary_name": payee.holder_name,
        "account_number": payee.account_number,
        "routing_number": payee.routing_number,
        "memo": payment.memo,
    }
    response = outbound.post("core-banking", "/disbursements", payload)
    confirmation = response.get("confirmation")
    if not confirmation:
        raise IntegrationError("core banking did not confirm the disbursement")
    return confirmation
