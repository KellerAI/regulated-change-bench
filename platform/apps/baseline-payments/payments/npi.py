"""Fields that hold nonpublic personal information (NPI), and how they are shown."""

NPI_FIELDS = frozenset(
    {
        "account_number",
        "routing_number",
        "tax_id",
        "date_of_birth",
    }
)

LAST_FOUR_FIELDS = frozenset({"account_number", "routing_number", "tax_id"})

REDACTED = "[redacted]"


def is_npi(field: str) -> bool:
    return field in NPI_FIELDS


def mask(field: str, value: str | None) -> str:
    """Display form: last four characters for numbers, nothing at all for other NPI."""
    if not value:
        return ""
    if field in LAST_FOUR_FIELDS and len(value) > 4:
        return "****" + value[-4:]
    return REDACTED
