"""HTTP route table. The app dispatches only through ROUTES."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    action: str
    mfa: bool


ROUTES = [
    Route("GET", "/health", "", mfa=False),
    Route("POST", "/payments", "create_payment", mfa=False),
    Route("POST", "/payments/{id}/approve", "approve_payment", mfa=True),
    Route("POST", "/payments/{id}/release", "release_payment", mfa=True),
    Route("GET", "/accounts/{id}", "view_account", mfa=False),
    Route("GET", "/accounts/{id}/number", "view_account_number", mfa=True),
    Route("POST", "/admin/users", "manage_users", mfa=True),
]
