from decimal import Decimal

import pytest

from payments import payments, policy
from payments.errors import Conflict, DuplicateApprovalError, SelfApprovalError
from payments.models import Actor

CORE_BANKING = "https://core.fernbrook.example/api/disbursements"
CENT = Decimal("0.01")


def roles_with(access_policy, action):
    return [role for role in access_policy["roles"] if access_policy["matrix"][role].get(action)]


@pytest.mark.control(obligation="MC-1", coverage="exhaustive", domain="payments.approver_pairs")
def test_maker_cannot_check(access_policy, policy_params, platform):
    store = platform.service.store
    payee = store.get_payee(platform.add_payee())
    now = platform.clock.now()
    threshold = Decimal(policy_params["payments.dual_control_threshold"])
    amounts = (Decimal("100.00"), threshold, threshold * 25)
    makers = roles_with(access_policy, "create_payment")
    checkers = roles_with(access_policy, "approve_payment")
    assert makers and checkers
    for maker_role in makers:
        for checker_role in checkers:
            for same_person in (True, False):
                for amount in amounts:
                    maker = Actor("maker.one", maker_role)
                    checker = Actor("maker.one" if same_person else "checker.one", checker_role)
                    payment = payments.create(store, maker, payee, amount, "USD", "", now)
                    if same_person:
                        with pytest.raises(SelfApprovalError):
                            payments.approve(store, checker, payment, now)
                        assert store.get_payment(payment.id).approvers == ()
                    else:
                        assert payments.approve(store, checker, payment, now).approvers == ("checker.one",)
    service_payment = platform.service.create_payment(platform.actor("officer.ben"), payee.id, "50.00")
    with pytest.raises(SelfApprovalError):
        platform.service.approve_payment(platform.actor("officer.ben"), service_payment.id)


def amount_grid(threshold):
    grid = {CENT, threshold - CENT, threshold, threshold + CENT}
    grid |= {policy.DUAL_CONTROL_THRESHOLD - CENT, policy.DUAL_CONTROL_THRESHOLD}
    steps = int(threshold * 3 / 100)
    grid |= {Decimal(100 * n) for n in range(1, steps + 1)}
    return sorted(amount for amount in grid if amount > 0)


@pytest.mark.control(obligation="PAY-1", coverage="exhaustive", domain="payments.amount_grid")
def test_dual_control_grid_matches_policy(policy_params, platform):
    threshold = Decimal(policy_params["payments.dual_control_threshold"])
    dual = policy_params["payments.dual_control_approvers"]
    assert policy.DUAL_CONTROL_THRESHOLD == threshold
    store = platform.service.store
    outbound = platform.service.outbound
    payee = store.get_payee(platform.add_payee())
    now = platform.clock.now()
    maker = Actor("maker.one", "clerk")
    first_checker = Actor("checker.one", "payments_officer")
    second_checker = Actor("checker.two", "treasury_manager")
    releaser = Actor("releaser.one", "treasury_manager")
    for amount in amount_grid(threshold):
        expected = dual if amount >= threshold else 1
        assert payments.required_approvals(amount) == expected, amount
        payment = payments.create(store, maker, payee, amount, "USD", "", now)
        with pytest.raises(SelfApprovalError):
            payments.approve(store, maker, payment, now)
        once = payments.approve(store, first_checker, payment, now)
        if expected == 1:
            assert once.status == "approved", amount
            continue
        assert once.status == "pending", amount
        with pytest.raises(DuplicateApprovalError):
            payments.approve(store, first_checker, once, now)
        with pytest.raises(Conflict):
            payments.release(store, releaser, once, outbound, now)
        twice = payments.approve(store, second_checker, once, now)
        assert twice.status == "approved", amount
    assert platform.transport.sent_to(CORE_BANKING) == []


@pytest.mark.control(obligation="PAY-2", coverage="sample", domain="payments.sampled_release")
def test_sampled_release_is_idempotent(platform):
    service = platform.service
    payee_id = platform.add_payee()
    payment = service.create_payment(platform.actor("clerk.ana"), payee_id, "12500.00", memo="Invoice 31")
    platform.approve_as_required(payment.id)
    first = service.release_payment(platform.actor("treasury.dee"), payment.id)
    second = service.release_payment(platform.actor("treasury.dee"), payment.id)
    assert second == first
    assert len(platform.transport.sent_to(CORE_BANKING)) == 1
    assert service.get_payment(platform.actor("auditor.fay"), payment.id).status == "released"
