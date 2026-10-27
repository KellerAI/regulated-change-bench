"""Roles, actions and grants. Anything not granted here is denied."""

from .errors import Forbidden

ROLES = (
    "clerk",
    "payments_officer",
    "treasury_manager",
    "auditor",
    "it_admin",
)

ACTIONS = (
    "create_payment",
    "approve_payment",
    "release_payment",
    "view_account",
    "view_account_number",
    "export_ledger",
    "manage_users",
    "view_audit",
    "rotate_keys",
    "purge_npi",
    "manage_payees",
    "view_reports",
)

STATE_CHANGING = {
    "create_payment",
    "approve_payment",
    "release_payment",
    "manage_users",
    "rotate_keys",
    "purge_npi",
    "manage_payees",
}

PRIVILEGED = {
    "approve_payment",
    "release_payment",
    "view_account_number",
    "export_ledger",
    "manage_users",
    "rotate_keys",
    "purge_npi",
    "manage_payees",
}

GRANTS = {
    ("clerk", "create_payment"),
    ("clerk", "view_account"),
    ("clerk", "view_reports"),
    ("payments_officer", "create_payment"),
    ("payments_officer", "approve_payment"),
    ("payments_officer", "view_account"),
    ("payments_officer", "view_account_number"),
    ("payments_officer", "manage_payees"),
    ("payments_officer", "view_reports"),
    ("treasury_manager", "approve_payment"),
    ("treasury_manager", "release_payment"),
    ("treasury_manager", "view_account"),
    ("treasury_manager", "view_account_number"),
    ("treasury_manager", "export_ledger"),
    ("treasury_manager", "view_reports"),
    ("auditor", "view_account"),
    ("auditor", "view_audit"),
    ("auditor", "view_reports"),
    ("auditor", "export_ledger"),
    ("it_admin", "manage_users"),
    ("it_admin", "rotate_keys"),
    ("it_admin", "purge_npi"),
    ("it_admin", "view_audit"),
}


def is_allowed(role: str, action: str) -> bool:
    return (role, action) in GRANTS


def require(role: str, action: str) -> None:
    if not is_allowed(role, action):
        raise Forbidden(f"role {role!r} may not {action}")
