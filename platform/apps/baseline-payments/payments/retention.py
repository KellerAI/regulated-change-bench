"""Disposal of NPI for closed payee accounts."""

from datetime import datetime

from . import policy
from .clock import months_before


def purge_due(store, now: datetime) -> list[int]:
    """Purge NPI of payees closed longer than the retention period. Returns the purged payee ids."""
    cutoff = months_before(now, policy.CLOSED_ACCOUNT_NPI_RETENTION_MONTHS)
    purged = []
    for payee in store.closed_payees_before(cutoff):
        if payee.legal_hold:
            continue
        store.purge_payee_npi(payee.id, now)
        purged.append(payee.id)
    return purged
