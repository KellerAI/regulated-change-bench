"""Payment operations. Each state-changing operation checks access and writes an audit event."""

from decimal import Decimal

from . import rbac
from .audit import AuditLog


class Denied(Exception):
    pass


class PaymentService:
    def __init__(self, clock):
        self.clock = clock
        self.audit = AuditLog()
        self.payments = {}

    def _check(self, user, action):
        if not rbac.is_allowed(user["role"], action):
            raise Denied(f"{user['id']} may not {action}")

    def create_payment(self, user, payment_id, amount):
        self._check(user, "create_payment")
        self.payments[payment_id] = {"amount": Decimal(amount), "creator": user["id"], "approvers": [],
                                     "state": "created"}
        self.audit.record(user["id"], "create_payment", payment_id, self.clock())
        return self.payments[payment_id]

    def approve_payment(self, user, payment_id):
        self._check(user, "approve_payment")
        p = self.payments[payment_id]
        if user["id"] == p["creator"]:
            raise Denied("creator may not approve")
        p["approvers"].append(user["id"])
        p["state"] = "approved"
        self.audit.record(user["id"], "approve_payment", payment_id, self.clock())
        return p
