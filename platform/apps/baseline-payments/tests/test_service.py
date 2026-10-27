from datetime import date, timedelta
from decimal import Decimal

import pytest

from payments import policy
from payments.errors import Conflict, Forbidden, IntegrationError, NotFound, ValidationError
from payments.logs import MemorySink
from support import CORE_BANKING, SCREENING, STATEMENTS, START, actor, details


def approved_payment(service, payee, amount="250.00"):
    payment = service.create_payment(actor("clerk.ana"), payee.id, amount, memo="Invoice 4471")
    service.approve_payment(actor("officer.ben"), payment.id)
    if Decimal(amount) >= policy.DUAL_CONTROL_THRESHOLD:
        service.approve_payment(actor("treasury.eli"), payment.id)
    return payment


def test_add_payee_screens_and_returns_a_masked_summary(service, transport):
    summary = service.add_payee(actor("officer.ben"), details())
    assert summary.account_number == "****5678"
    assert transport.sent_to(SCREENING) == [{"name": "Northwind Office Supply"}]


def test_screening_match_refuses_the_payee(service, transport):
    transport.reply(SCREENING, {"result": "match"})
    with pytest.raises(ValidationError):
        service.add_payee(actor("officer.ben"), details())
    assert service.store.payee_ids() == []


def test_screening_outage_is_reported(service, transport):
    transport.fail(SCREENING)
    with pytest.raises(IntegrationError):
        service.add_payee(actor("officer.ben"), details())


def test_clerk_cannot_add_payees(service):
    with pytest.raises(Forbidden):
        service.add_payee(actor("clerk.ana"), details())


def test_payment_end_to_end(service, payee, transport):
    payment = approved_payment(service, payee, amount="12500.00")
    release = service.release_payment(actor("treasury.dee"), payment.id)
    assert release.released_by == "treasury.dee"
    assert service.get_payment(actor("auditor.fay"), payment.id).status == "released"
    assert len(transport.sent_to(CORE_BANKING)) == 1


def test_release_failure_is_logged_without_npi(service, payee, transport):
    payment = approved_payment(service, payee)
    transport.fail(CORE_BANKING)
    sink = MemorySink().attach()
    try:
        with pytest.raises(IntegrationError):
            service.release_payment(actor("treasury.dee"), payment.id)
    finally:
        sink.detach()
    assert any("payment release failed" in line for line in sink.lines)
    assert "880012345678" not in sink.text()


def test_only_listed_roles_act(service, payee):
    payment = service.create_payment(actor("clerk.ana"), payee.id, "100.00")
    with pytest.raises(Forbidden):
        service.approve_payment(actor("clerk.ana"), payment.id)
    with pytest.raises(Forbidden):
        service.release_payment(actor("officer.ben"), payment.id)
    with pytest.raises(Forbidden):
        service.create_payment(actor("auditor.fay"), payee.id, "100.00")


def test_amend_memo(service, payee):
    payment = service.create_payment(actor("clerk.ana"), payee.id, "100.00", memo="Invoice 1")
    assert service.amend_memo(actor("clerk.ana"), payment.id, "Invoice 2").memo == "Invoice 2"


def test_payee_lookup_and_search(service, payee):
    assert service.get_payee(actor("clerk.ana"), payee.id).holder_name == "Northwind Office Supply"
    assert [s.id for s in service.search_payees(actor("clerk.ana"), "North")] == [payee.id]


def test_reveal_account_number(service, payee):
    assert service.reveal_account_number(actor("treasury.dee"), payee.id) == "880012345678"
    with pytest.raises(Forbidden):
        service.reveal_account_number(actor("clerk.ana"), payee.id)


def test_close_payee_twice_is_a_conflict(service, payee):
    assert service.close_payee(actor("officer.ben"), payee.id).status == "closed"
    with pytest.raises(Conflict):
        service.close_payee(actor("officer.ben"), payee.id)


def test_legal_hold(service, payee):
    assert service.set_legal_hold(actor("admin.gus"), payee.id, True).legal_hold
    assert not service.set_legal_hold(actor("admin.gus"), payee.id, False).legal_hold
    with pytest.raises(NotFound):
        service.set_legal_hold(actor("admin.gus"), 999, True)


def test_daily_totals(service, payee):
    payment = approved_payment(service, payee)
    service.release_payment(actor("treasury.dee"), payment.id)
    service.create_payment(actor("clerk.ana"), payee.id, "40.00")
    [totals] = service.daily_totals(actor("auditor.fay"), date(2026, 9, 1))
    assert totals.created_count == 2
    assert totals.released_count == 1
    assert str(totals.released_amount) == "250.00"


def test_statement_export_and_delivery(service, payee, transport):
    approved_payment(service, payee)
    text = service.export_statement(actor("clerk.ana"), payee.id, 2026, 9)
    assert "account,****5678" in text
    reply = service.deliver_statement(actor("clerk.ana"), payee.id, 2026, 9)
    assert reply["accepted"]
    [sent] = transport.sent_to(STATEMENTS)
    assert sent["period"] == "2026-09"
    assert "880012345678" not in sent["document"]


def test_ledger_export_is_audited(service, payee):
    approved_payment(service, payee)
    text = service.export_ledger(actor("treasury.dee"))
    assert text.count("\n") == 2
    assert service.audit_events(actor("auditor.fay"))[-1].action == "export_ledger"


def test_add_user(service):
    user = service.add_user(actor("admin.gus"), "clerk.hal", "clerk")
    assert user.role == "clerk"
    with pytest.raises(ValidationError):
        service.add_user(actor("admin.gus"), "x", "superuser")


def test_rotate_keys_reseals(service, payee):
    assert service.rotate_keys(actor("admin.gus")) == 2
    raw = service.store.connection.execute("SELECT tax_id FROM payees").fetchone()[0]
    assert raw.startswith("llv2:")
    assert service.reveal_account_number(actor("treasury.dee"), payee.id) == "880012345678"


def test_run_retention(service, clock, payee):
    service.close_payee(actor("officer.ben"), payee.id)
    clock.advance(days=365 * 8)
    result = service.run_retention(actor("admin.gus"))
    assert result["payees_purged"] == [payee.id]
    with pytest.raises(NotFound):
        service.reveal_account_number(actor("treasury.dee"), payee.id)


def test_audit_trail_verifies(service, payee):
    approved_payment(service, payee)
    assert service.audit_log.verify()
    actions = [e.action for e in service.audit_events(actor("auditor.fay"))]
    assert actions == ["add_payee", "create_payment", "approve_payment"]


def test_clock_drives_timestamps(service, clock, payee):
    clock.advance(hours=2)
    payment = service.create_payment(actor("clerk.ana"), payee.id, "5.00")
    assert payment.created_at == START + timedelta(hours=2)
