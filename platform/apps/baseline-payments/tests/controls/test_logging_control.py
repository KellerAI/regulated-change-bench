import pytest

from payments.logs import MemorySink

CORE_BANKING = "https://core.fernbrook.example/api/disbursements"
SCREENING = "https://screening.fernbrook.example/v1/screen"


def run_sampled_flows(platform):
    service = platform.service
    payee_id = platform.add_payee("Harbor Freight Lines")
    platform.transport.reply(SCREENING, {"result": "match"})
    with pytest.raises(Exception):
        platform.add_payee("Blocked Trading Co")
    platform.transport.reply(SCREENING, {"result": "clear"})
    released = service.create_payment(platform.actor("clerk.ana"), payee_id, "12500.00", memo="Invoice 31")
    platform.approve_as_required(released.id)
    service.release_payment(platform.actor("treasury.dee"), released.id)
    failing = service.create_payment(platform.actor("clerk.ana"), payee_id, "800.00", memo="Invoice 32")
    platform.approve_as_required(failing.id)
    platform.transport.fail(CORE_BANKING)
    with pytest.raises(Exception):
        service.release_payment(platform.actor("treasury.dee"), failing.id)
    service.reveal_account_number(platform.actor("treasury.dee"), payee_id)
    service.deliver_statement(platform.actor("clerk.ana"), payee_id, 2026, 9)
    service.rotate_keys(platform.actor("admin.gus"))


@pytest.mark.control(obligation="LOG-1", coverage="sample", domain="payments.sampled_flows")
def test_sampled_flows_do_not_log_npi(platform, npi_sample):
    sink = MemorySink().attach()
    try:
        run_sampled_flows(platform)
    finally:
        sink.detach()
    text = sink.text()
    assert "payment release failed" in text
    for field, value in npi_sample.items():
        assert value not in text, field
