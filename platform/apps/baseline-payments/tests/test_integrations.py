import pytest

from payments.errors import IntegrationError
from payments.integrations import INTEGRATIONS, OutboundClient, find
from payments.transports import RecordingTransport, UrllibTransport


def test_names_are_unique():
    names = [i.name for i in INTEGRATIONS]
    assert len(names) == len(set(names))


def test_find():
    assert find("core-banking").base_url.endswith("/api")
    with pytest.raises(KeyError):
        find("unknown")


def test_client_joins_paths():
    client = OutboundClient(RecordingTransport())
    assert client.url_for("core-banking", "/disbursements") == "https://core.fernbrook.example/api/disbursements"
    assert client.url_for("core-banking", "disbursements") == "https://core.fernbrook.example/api/disbursements"


def test_client_posts_through_the_transport():
    transport = RecordingTransport()
    reply = OutboundClient(transport).post("sanctions-screening", "/screen", {"name": "Northwind"})
    assert reply["result"] == "clear"
    assert transport.requests == [("https://screening.fernbrook.example/v1/screen", {"name": "Northwind"})]


def test_recording_transport_failures_and_replies():
    transport = RecordingTransport()
    transport.fail("https://x.example/a")
    with pytest.raises(IntegrationError):
        transport.send("https://x.example/a", {})
    transport.recover("https://x.example/a")
    transport.reply("https://x.example/a", {"ok": True})
    assert transport.send("https://x.example/a", {}) == {"ok": True}


def test_urllib_transport_wraps_request_errors():
    with pytest.raises(IntegrationError):
        UrllibTransport().send("https://[malformed/path", {})
