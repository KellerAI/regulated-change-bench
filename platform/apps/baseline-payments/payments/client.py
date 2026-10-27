"""In-process HTTP client for the WSGI app, for scripts and local checks."""

import io
import json
from dataclasses import dataclass
from wsgiref.util import setup_testing_defaults


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> object:
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")


class WsgiClient:
    def __init__(self, app) -> None:
        self._app = app

    def get(self, path: str, token: str | None = None) -> Response:
        return self.request("GET", path, token)

    def post(self, path: str, token: str | None = None, body: dict | None = None) -> Response:
        return self.request("POST", path, token, body)

    def put(self, path: str, token: str | None = None, body: dict | None = None) -> Response:
        return self.request("PUT", path, token, body)

    def request(self, method: str, path: str, token: str | None = None, body: dict | None = None) -> Response:
        environ = self._environ(method, path, token, body)
        captured: dict = {}

        def start_response(status: str, headers: list, exc_info=None) -> None:
            captured["status"] = status
            captured["headers"] = dict(headers)

        chunks = self._app(environ, start_response)
        status = int(captured["status"].split(" ", 1)[0])
        return Response(status, captured["headers"], b"".join(chunks))

    def _environ(self, method: str, path: str, token: str | None, body: dict | None) -> dict:
        data = b"" if body is None else json.dumps(body).encode("utf-8")
        path_info, _, query = path.partition("?")
        environ: dict = {}
        setup_testing_defaults(environ)
        environ["REQUEST_METHOD"] = method
        environ["PATH_INFO"] = path_info
        environ["QUERY_STRING"] = query
        environ["CONTENT_TYPE"] = "application/json"
        environ["CONTENT_LENGTH"] = str(len(data))
        environ["wsgi.input"] = io.BytesIO(data)
        if token is not None:
            environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return environ
