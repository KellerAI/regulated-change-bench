from urllib.parse import urlsplit

import pytest

from payments.integrations import INTEGRATIONS, OutboundClient
from payments.transports import RecordingTransport


@pytest.mark.control(obligation="ENC-2", coverage="exhaustive", domain="payments.integrations")
def test_integrations_use_tls():
    assert INTEGRATIONS
    insecure = []
    for integration in INTEGRATIONS:
        parts = urlsplit(integration.base_url)
        if parts.scheme != "https" or not parts.hostname:
            insecure.append(integration.name)
    assert insecure == []
    for integration in INTEGRATIONS:
        transport = RecordingTransport()
        OutboundClient(transport).post(integration.name, "/probe", {})
        [(url, _)] = transport.requests
        assert urlsplit(url).scheme == "https", integration.name
        assert urlsplit(url).hostname == urlsplit(integration.base_url).hostname, integration.name


@pytest.mark.control(obligation="INV-1", coverage="exhaustive", domain="payments.integrations")
def test_integrations_are_inventoried(asset_inventory):
    names = [integration.name for integration in INTEGRATIONS]
    assert len(names) == len(set(names))
    entries = {entry["name"]: entry for entry in asset_inventory["integrations"]}
    classifications = set(asset_inventory["classifications"])
    problems = []
    for integration in INTEGRATIONS:
        entry = entries.get(integration.name)
        if entry is None:
            problems.append((integration.name, "not in inventory"))
            continue
        if entry.get("host") != urlsplit(integration.base_url).hostname:
            problems.append((integration.name, "host differs from inventory"))
        if not entry.get("owner"):
            problems.append((integration.name, "no owner"))
        if entry.get("data_classification") not in classifications:
            problems.append((integration.name, "no valid classification"))
    assert problems == []
