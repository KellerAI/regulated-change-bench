"""Outbound integrations. Every external system the service calls is listed here."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Integration:
    name: str
    base_url: str


INTEGRATIONS = [
    Integration("core-banking", "https://core.fernbrook.example/api"),
    Integration("sanctions-screening", "https://screening.fernbrook.example/v1"),
    Integration("statement-delivery", "https://statements.fernbrook.example/v1"),
]


def find(name: str) -> Integration:
    for integration in INTEGRATIONS:
        if integration.name == name:
            return integration
    raise KeyError(f"unknown integration {name!r}")


class OutboundClient:
    """Sends JSON requests to listed integrations through a transport."""

    def __init__(self, transport) -> None:
        self._transport = transport

    def url_for(self, name: str, path: str) -> str:
        integration = find(name)
        return integration.base_url.rstrip("/") + "/" + path.lstrip("/")

    def post(self, name: str, path: str, payload: dict) -> dict:
        return self._transport.send(self.url_for(name, path), payload)
