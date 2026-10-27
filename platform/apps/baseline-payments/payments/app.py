"""WSGI front end. Requests are dispatched only through the route table."""

import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import parse_qs

from . import rbac, statements
from .errors import (
    LedgerError,
    MethodNotAllowed,
    MfaRequired,
    NotFound,
    SessionExpired,
    Unauthenticated,
    ValidationError,
)
from .logs import AppLog
from .models import Actor, PayeeDetails
from .routes import ROUTES, Route
from .session import Session, SessionStore

MAX_BODY_BYTES = 64 * 1024

STATUS_LINES = {
    "unauthenticated": "401 Unauthorized",
    "session_expired": "401 Unauthorized",
    "mfa_required": "403 Forbidden",
    "forbidden": "403 Forbidden",
    "self_approval": "403 Forbidden",
    "not_found": "404 Not Found",
    "method_not_allowed": "405 Method Not Allowed",
    "invalid_request": "400 Bad Request",
    "conflict": "409 Conflict",
    "duplicate_approval": "409 Conflict",
    "integration_failed": "502 Bad Gateway",
}


@dataclass(frozen=True)
class Request:
    actor: Actor | None
    path_id: int | None
    query: dict[str, str]
    body: dict


def _compile(pattern: str) -> re.Pattern:
    regex = re.escape(pattern).replace(r"\{id\}", r"(?P<id>[0-9]+)")
    return re.compile(f"^{regex}$")


ROUTE_TABLE = [(route, _compile(route.pattern)) for route in ROUTES]


def match(method: str, path: str) -> tuple[Route, int | None]:
    path_known = False
    for route, regex in ROUTE_TABLE:
        found = regex.match(path)
        if found is None:
            continue
        if route.method != method:
            path_known = True
            continue
        path_id = found.groupdict().get("id")
        return route, None if path_id is None else int(path_id)
    if path_known:
        raise MethodNotAllowed(f"{method} is not allowed on {path}")
    raise NotFound(f"no route for {path}")


class LedgerApp:
    def __init__(self, service, sessions: SessionStore, clock, log: AppLog | None = None) -> None:
        self._service = service
        self._sessions = sessions
        self._clock = clock
        self._log = log or AppLog()

    def __call__(self, environ: dict, start_response) -> list[bytes]:
        try:
            status, payload = self.handle(environ)
        except LedgerError as exc:
            status = STATUS_LINES.get(exc.code, "400 Bad Request")
            payload = {"error": exc.code, "message": str(exc)}
        except Exception:
            self._log.error("unhandled error", method=environ.get("REQUEST_METHOD"), path=environ.get("PATH_INFO"))
            status = "500 Internal Server Error"
            payload = {"error": "internal_error"}
        return _respond(start_response, status, payload)

    def handle(self, environ: dict) -> tuple[str, object]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO") or "/"
        route, path_id = match(method, path)
        actor = self._authenticate(environ, route)
        request = Request(actor, path_id, _query(environ), _body(environ, method))
        handler = HANDLERS[route.key]
        return handler(self._service, request)

    def _authenticate(self, environ: dict, route: Route) -> Actor | None:
        if route.action is None:
            return None
        session = self._session(environ)
        now = self._clock.now()
        if not session.is_active(now, route.action in rbac.PRIVILEGED):
            raise SessionExpired("the session has been idle for too long")
        if route.mfa and not session.mfa_verified:
            raise MfaRequired("this action needs multi-factor authentication")
        rbac.require(session.role, route.action)
        session.touch(now)
        return Actor(session.user_id, session.role)

    def _session(self, environ: dict) -> Session:
        scheme, _, token = environ.get("HTTP_AUTHORIZATION", "").partition(" ")
        if scheme != "Bearer" or not token:
            raise Unauthenticated("a bearer token is required")
        session = self._sessions.get(token)
        if session is None:
            raise Unauthenticated("unknown session")
        return session


# request and response helpers ------------------------------------------------


def _query(environ: dict) -> dict[str, str]:
    parsed = parse_qs(environ.get("QUERY_STRING", ""))
    return {key: values[0] for key, values in parsed.items()}


def _body(environ: dict, method: str) -> dict:
    if method == "GET":
        return {}
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError as exc:
        raise ValidationError("invalid Content-Length") from exc
    if length > MAX_BODY_BYTES:
        raise ValidationError("request body is too large")
    raw = environ["wsgi.input"].read(length) if length > 0 else b""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValidationError("request body must be JSON") from exc
    if not isinstance(data, dict):
        raise ValidationError("request body must be a JSON object")
    return data


def _plain(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _respond(start_response, status: str, payload: object) -> list[bytes]:
    if isinstance(payload, str):
        body = payload.encode("utf-8")
        content_type = "text/csv; charset=utf-8"
    else:
        body = json.dumps(_plain(payload), sort_keys=True).encode("utf-8")
        content_type = "application/json"
    start_response(status, [("Content-Type", content_type), ("Content-Length", str(len(body)))])
    return [body]


def _field(body: dict, name: str) -> object:
    if name not in body:
        raise ValidationError(f"{name} is required")
    return body[name]


def _int_field(body: dict, name: str) -> int:
    value = _field(body, name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"{name} must be an integer")
    return value


def _period(query: dict[str, str]) -> tuple[int, int]:
    return statements.parse_period(query.get("period", ""))


def _day(query: dict[str, str]) -> date:
    try:
        return date.fromisoformat(query.get("day", ""))
    except ValueError as exc:
        raise ValidationError("day must be YYYY-MM-DD") from exc


# handlers --------------------------------------------------------------------


def _health(service, request: Request):
    return "200 OK", {"status": "ok"}


def _list_payments(service, request: Request):
    return "200 OK", service.list_payments(request.actor)


def _create_payment(service, request: Request):
    body = request.body
    payment = service.create_payment(
        request.actor,
        _int_field(body, "payee_id"),
        _field(body, "amount"),
        memo=body.get("memo", ""),
        currency=body.get("currency", "USD"),
        instruction_id=body.get("instruction_id"),
    )
    return "201 Created", payment


def _get_payment(service, request: Request):
    return "200 OK", service.get_payment(request.actor, request.path_id)


def _amend_memo(service, request: Request):
    memo = _field(request.body, "memo")
    return "200 OK", service.amend_memo(request.actor, request.path_id, memo)


def _approve_payment(service, request: Request):
    return "200 OK", service.approve_payment(request.actor, request.path_id)


def _release_payment(service, request: Request):
    return "200 OK", service.release_payment(request.actor, request.path_id)


def _search_payees(service, request: Request):
    return "200 OK", service.search_payees(request.actor, request.query.get("name", ""))


def _add_payee(service, request: Request):
    body = request.body
    details = PayeeDetails(
        holder_name=str(_field(body, "holder_name")),
        category=str(_field(body, "category")),
        account_number=str(_field(body, "account_number")),
        routing_number=str(_field(body, "routing_number")),
        tax_id=str(_field(body, "tax_id")),
        date_of_birth=body.get("date_of_birth"),
    )
    return "201 Created", service.add_payee(request.actor, details)


def _get_payee(service, request: Request):
    return "200 OK", service.get_payee(request.actor, request.path_id)


def _reveal_account_number(service, request: Request):
    number = service.reveal_account_number(request.actor, request.path_id)
    return "200 OK", {"payee_id": request.path_id, "account_number": number}


def _close_payee(service, request: Request):
    return "200 OK", service.close_payee(request.actor, request.path_id)


def _set_legal_hold(service, request: Request):
    hold = _field(request.body, "hold")
    if not isinstance(hold, bool):
        raise ValidationError("hold must be true or false")
    return "200 OK", service.set_legal_hold(request.actor, request.path_id, hold)


def _export_statement(service, request: Request):
    year, month = _period(request.query)
    return "200 OK", service.export_statement(request.actor, request.path_id, year, month)


def _deliver_statement(service, request: Request):
    year, month = statements.parse_period(str(_field(request.body, "period")))
    return "202 Accepted", service.deliver_statement(request.actor, request.path_id, year, month)


def _daily_totals(service, request: Request):
    return "200 OK", service.daily_totals(request.actor, _day(request.query))


def _export_ledger(service, request: Request):
    return "200 OK", service.export_ledger(request.actor)


def _audit_events(service, request: Request):
    return "200 OK", service.audit_events(request.actor)


def _add_user(service, request: Request):
    body = request.body
    user = service.add_user(request.actor, str(_field(body, "user_id")), str(_field(body, "role")))
    return "201 Created", user


def _rotate_keys(service, request: Request):
    return "200 OK", {"key_version": service.rotate_keys(request.actor)}


def _run_retention(service, request: Request):
    return "200 OK", service.run_retention(request.actor)


HANDLERS = {
    "GET /health": _health,
    "GET /payments": _list_payments,
    "POST /payments": _create_payment,
    "GET /payments/{id}": _get_payment,
    "PUT /payments/{id}/memo": _amend_memo,
    "POST /payments/{id}/approve": _approve_payment,
    "POST /payments/{id}/release": _release_payment,
    "GET /payees": _search_payees,
    "POST /payees": _add_payee,
    "GET /payees/{id}": _get_payee,
    "GET /payees/{id}/account-number": _reveal_account_number,
    "POST /payees/{id}/close": _close_payee,
    "POST /payees/{id}/legal-hold": _set_legal_hold,
    "GET /payees/{id}/statement": _export_statement,
    "POST /payees/{id}/statement/deliver": _deliver_statement,
    "GET /reports/daily-totals": _daily_totals,
    "GET /ledger/export": _export_ledger,
    "GET /audit/events": _audit_events,
    "POST /users": _add_user,
    "POST /keys/rotate": _rotate_keys,
    "POST /retention/run": _run_retention,
}
