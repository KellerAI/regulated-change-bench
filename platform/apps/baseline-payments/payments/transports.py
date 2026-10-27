"""Transports that carry outbound integration requests."""

import json
import ssl
import urllib.error
import urllib.request

from .errors import IntegrationError

DEFAULT_TIMEOUT_SECONDS = 10


class UrllibTransport:
    """JSON over HTTPS with the standard library and certificate verification."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._context = ssl.create_default_context()

    def send(self, url: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=self._timeout, context=self._context) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise IntegrationError(f"request to {url} failed") from exc


class RecordingTransport:
    """In-process transport for local runs: records requests and returns canned replies."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict]] = []
        self._replies: dict[str, dict] = {}
        self._failing: set[str] = set()

    def reply(self, url: str, response: dict) -> None:
        self._replies[url] = response

    def fail(self, url: str) -> None:
        self._failing.add(url)

    def recover(self, url: str) -> None:
        self._failing.discard(url)

    def sent_to(self, url: str) -> list[dict]:
        return [payload for target, payload in self.requests if target == url]

    def send(self, url: str, payload: dict) -> dict:
        self.requests.append((url, payload))
        if url in self._failing:
            raise IntegrationError(f"request to {url} failed")
        if url in self._replies:
            return self._replies[url]
        return {"confirmation": f"CONF-{len(self.requests):06d}", "result": "clear", "accepted": True}
