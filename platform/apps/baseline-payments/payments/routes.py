"""HTTP route table. The app serves these routes and nothing else."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    method: str
    pattern: str
    action: str | None
    mfa: bool = False

    @property
    def key(self) -> str:
        return f"{self.method} {self.pattern}"


ROUTES = [
    Route("GET", "/health", None, mfa=False),
    Route("GET", "/payments", "view_account", mfa=False),
    Route("POST", "/payments", "create_payment", mfa=False),
    Route("GET", "/payments/{id}", "view_account", mfa=False),
    Route("PUT", "/payments/{id}/memo", "create_payment", mfa=False),
    Route("POST", "/payments/{id}/approve", "approve_payment", mfa=True),
    Route("POST", "/payments/{id}/release", "release_payment", mfa=True),
    Route("GET", "/payees", "view_account", mfa=False),
    Route("POST", "/payees", "manage_payees", mfa=True),
    Route("GET", "/payees/{id}", "view_account", mfa=False),
    Route("GET", "/payees/{id}/account-number", "view_account_number", mfa=True),
    Route("POST", "/payees/{id}/close", "manage_payees", mfa=True),
    Route("POST", "/payees/{id}/legal-hold", "purge_npi", mfa=True),
    Route("GET", "/payees/{id}/statement", "view_reports", mfa=False),
    Route("POST", "/payees/{id}/statement/deliver", "view_reports", mfa=False),
    Route("GET", "/reports/daily-totals", "view_reports", mfa=False),
    Route("GET", "/ledger/export", "export_ledger", mfa=True),
    Route("GET", "/audit/events", "view_audit", mfa=False),
    Route("POST", "/users", "manage_users", mfa=True),
    Route("POST", "/keys/rotate", "rotate_keys", mfa=True),
    Route("POST", "/retention/run", "purge_npi", mfa=True),
]
