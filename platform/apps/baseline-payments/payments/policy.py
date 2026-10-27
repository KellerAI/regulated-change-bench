"""Approved operating parameters for payment disbursement."""

from decimal import Decimal

DUAL_CONTROL_THRESHOLD = Decimal("10000.00")
PRIVILEGED_IDLE_MINUTES = 15
STANDARD_IDLE_MINUTES = 30
AUDIT_RETENTION_YEARS = 7
CLOSED_ACCOUNT_NPI_RETENTION_MONTHS = 84
