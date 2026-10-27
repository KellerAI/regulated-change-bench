"""Errors the service reports to its callers."""


class LedgerError(Exception):
    """Base class. `code` is a stable, machine-readable name for the error."""

    code = "error"


class Unauthenticated(LedgerError):
    code = "unauthenticated"


class SessionExpired(Unauthenticated):
    code = "session_expired"


class MfaRequired(LedgerError):
    code = "mfa_required"


class Forbidden(LedgerError):
    code = "forbidden"


class NotFound(LedgerError):
    code = "not_found"


class MethodNotAllowed(LedgerError):
    code = "method_not_allowed"


class ValidationError(LedgerError):
    code = "invalid_request"


class Conflict(LedgerError):
    code = "conflict"


class SelfApprovalError(LedgerError):
    code = "self_approval"


class DuplicateApprovalError(LedgerError):
    code = "duplicate_approval"


class IntegrationError(LedgerError):
    code = "integration_failed"
