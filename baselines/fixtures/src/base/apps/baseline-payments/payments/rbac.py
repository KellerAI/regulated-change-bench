"""Role-based access: explicit grants, default deny."""

ROLES = ("clerk", "payments_officer", "treasury_manager", "auditor", "it_admin")

ACTIONS = (
    "create_payment",
    "approve_payment",
    "release_payment",
    "view_account",
    "view_account_number",
    "view_audit",
    "manage_users",
)

GRANTS = {
    ("clerk", "create_payment"),
    ("clerk", "view_account"),
    ("payments_officer", "approve_payment"),
    ("payments_officer", "view_account"),
    ("payments_officer", "view_account_number"),
    ("treasury_manager", "approve_payment"),
    ("treasury_manager", "release_payment"),
    ("treasury_manager", "view_account"),
    ("auditor", "view_account"),
    ("auditor", "view_audit"),
    ("it_admin", "manage_users"),
}

STATE_CHANGING = frozenset({"create_payment", "approve_payment", "release_payment", "manage_users"})

PRIVILEGED = frozenset({"approve_payment", "release_payment", "view_account_number", "manage_users"})


def is_allowed(role, action):
    return (role, action) in GRANTS
