import logging

from payments.logs import AppLog, MemorySink, format_entry, mask_fields


def test_npi_fields_are_masked():
    masked = mask_fields({"account_number": "880012345678", "date_of_birth": "1975-03-14", "payee_id": 7})
    assert masked == {"account_number": "****5678", "date_of_birth": "[redacted]", "payee_id": 7}


def test_missing_npi_value():
    assert mask_fields({"tax_id": None}) == {"tax_id": ""}


def test_format_entry_sorts_fields():
    assert format_entry("payee added", {"b": 2, "a": 1}) == "payee added a=1 b=2"


def test_app_log_writes_masked_lines():
    sink = MemorySink().attach("payments")
    try:
        AppLog().error("release failed", account_number="880012345678", payment_id=3)
    finally:
        sink.detach()
    assert sink.lines == ["release failed account_number=****5678 payment_id=3"]


def test_sink_detach_restores_level():
    logger = logging.getLogger("payments.sinktest")
    logger.setLevel(logging.WARNING)
    sink = MemorySink().attach("payments.sinktest")
    assert logger.level == logging.DEBUG
    sink.detach()
    assert logger.level == logging.WARNING
    assert sink not in logger.handlers
    sink.detach()
