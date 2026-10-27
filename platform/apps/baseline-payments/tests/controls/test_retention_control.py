import pytest


@pytest.mark.control(obligation="RET-1", coverage="sample", domain="payments.sampled_payees")
def test_sampled_purge_respects_hold(platform):
    service = platform.service
    officer = platform.actor("officer.ben")
    admin = platform.actor("admin.gus")
    expired = platform.add_payee("Expired Vendor")
    held = platform.add_payee("Held Vendor")
    recent = platform.add_payee("Recent Vendor")
    service.close_payee(officer, expired)
    service.close_payee(officer, held)
    service.set_legal_hold(admin, held, True)
    platform.clock.advance(days=365 * 11)
    service.close_payee(officer, recent)
    platform.clock.advance(days=365)
    result = service.run_retention(admin)
    assert result["payees_purged"] == [expired]
    store = service.store
    assert store.get_payee(expired).account_number is None
    assert store.get_payee(expired).tax_id is None
    assert store.get_payee(held).account_number is not None
    assert store.get_payee(recent).account_number is not None
