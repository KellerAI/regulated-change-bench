"""Service operations behind the HTTP layer and the batch jobs."""

from datetime import date

from . import directory, payments, rbac, reports, retention, statements
from .audit import AuditEvent, AuditLog
from .directory import PayeeSummary
from .errors import Conflict, IntegrationError, NotFound, ValidationError
from .integrations import OutboundClient
from .logs import AppLog
from .models import Actor, PayeeDetails, Payment, Release, User
from .reports import DailyTotals
from .store import Store
from .vault import Vault


class LedgerService:
    def __init__(
        self,
        store: Store,
        audit_log: AuditLog,
        outbound: OutboundClient,
        clock,
        log: AppLog,
        vault: Vault,
    ) -> None:
        self._store = store
        self._audit_log = audit_log
        self._outbound = outbound
        self._clock = clock
        self._log = log
        self._vault = vault

    @property
    def store(self) -> Store:
        return self._store

    @property
    def audit_log(self) -> AuditLog:
        return self._audit_log

    @property
    def outbound(self) -> OutboundClient:
        return self._outbound

    # users -----------------------------------------------------------------

    def add_user(self, actor: Actor, user_id: str, role: str) -> User:
        self._authorize(actor, "manage_users")
        if role not in rbac.ROLES:
            raise ValidationError(f"unknown role {role!r}")
        user = self._store.add_user(user_id, role)
        self._audit(actor, "add_user", f"user:{user_id}")
        return user

    # payee directory -------------------------------------------------------

    def add_payee(self, actor: Actor, details: PayeeDetails) -> PayeeSummary:
        self._authorize(actor, "manage_payees")
        clean = directory.validate(details)
        self._screen(clean)
        payee = self._store.add_payee(clean, actor.user_id, self._clock.now())
        self._audit(actor, "add_payee", f"payee:{payee.id}")
        self._log.info("payee added", payee_id=payee.id, category=payee.category)
        return directory.summarize(payee)

    def get_payee(self, actor: Actor, payee_id: int) -> PayeeSummary:
        self._authorize(actor, "view_account")
        return directory.summarize(self._store.get_payee(payee_id))

    def search_payees(self, actor: Actor, prefix: str = "") -> list[PayeeSummary]:
        self._authorize(actor, "view_account")
        return directory.search(self._store, prefix)

    def reveal_account_number(self, actor: Actor, payee_id: int) -> str:
        self._authorize(actor, "view_account_number")
        payee = self._store.get_payee(payee_id)
        if payee.account_number is None:
            raise NotFound("the account number has been purged")
        self._audit(actor, "reveal_account_number", f"payee:{payee_id}")
        return payee.account_number

    def close_payee(self, actor: Actor, payee_id: int) -> PayeeSummary:
        self._authorize(actor, "manage_payees")
        if self._store.get_payee(payee_id).status != "open":
            raise Conflict("payee is already closed")
        payee = self._store.close_payee(payee_id, self._clock.now())
        self._audit(actor, "close_payee", f"payee:{payee_id}")
        return directory.summarize(payee)

    def set_legal_hold(self, actor: Actor, payee_id: int, hold: bool) -> PayeeSummary:
        self._authorize(actor, "purge_npi")
        self._store.get_payee(payee_id)
        payee = self._store.set_legal_hold(payee_id, hold)
        self._audit(actor, "set_legal_hold", f"payee:{payee_id}")
        return directory.summarize(payee)

    def _screen(self, details: PayeeDetails) -> None:
        try:
            response = self._outbound.post("sanctions-screening", "/screen", {"name": details.holder_name})
        except IntegrationError:
            self._log.error("payee screening unavailable", category=details.category)
            raise
        if response.get("result") != "clear":
            self._log.warning("payee screening returned a match", category=details.category)
            raise ValidationError("payee did not pass sanctions screening")

    # payments --------------------------------------------------------------

    def create_payment(
        self,
        actor: Actor,
        payee_id: int,
        amount: object,
        memo: str = "",
        currency: str = "USD",
        instruction_id: str | None = None,
    ) -> Payment:
        self._authorize(actor, "create_payment")
        payee = self._store.get_payee(payee_id)
        value = payments.parse_amount(amount)
        now = self._clock.now()
        payment = payments.create(self._store, actor, payee, value, currency, memo, now, instruction_id)
        self._audit(actor, "create_payment", f"payment:{payment.id}")
        return payment

    def amend_memo(self, actor: Actor, payment_id: int, memo: str) -> Payment:
        self._authorize(actor, "create_payment")
        payment = self._store.get_payment(payment_id)
        updated = payments.amend_memo(self._store, actor, payment, memo)
        self._audit(actor, "amend_memo", f"payment:{payment_id}")
        return updated

    def approve_payment(self, actor: Actor, payment_id: int) -> Payment:
        self._authorize(actor, "approve_payment")
        payment = self._store.get_payment(payment_id)
        updated = payments.approve(self._store, actor, payment, self._clock.now())
        self._audit(actor, "approve_payment", f"payment:{payment_id}")
        return updated

    def release_payment(self, actor: Actor, payment_id: int) -> Release:
        self._authorize(actor, "release_payment")
        payment = self._store.get_payment(payment_id)
        try:
            result = payments.release(self._store, actor, payment, self._outbound, self._clock.now())
        except IntegrationError:
            self._log.error("payment release failed", payment_id=payment.id, instruction_id=payment.instruction_id)
            raise
        self._audit(actor, "release_payment", f"payment:{payment_id}")
        return result

    def get_payment(self, actor: Actor, payment_id: int) -> Payment:
        self._authorize(actor, "view_account")
        return self._store.get_payment(payment_id)

    def list_payments(self, actor: Actor) -> list[Payment]:
        self._authorize(actor, "view_account")
        return self._store.list_payments()

    # reports ---------------------------------------------------------------

    def daily_totals(self, actor: Actor, day: date) -> list[DailyTotals]:
        self._authorize(actor, "view_reports")
        start, end = reports.day_bounds(day)
        created = self._store.payments_created_between(start, end)
        releases = self._store.releases_between(start, end)
        released = [self._store.get_payment(r.payment_id) for r in releases]
        return reports.daily_totals(day, created, released)

    def export_statement(self, actor: Actor, payee_id: int, year: int, month: int) -> str:
        self._authorize(actor, "view_reports")
        payee = self._store.get_payee(payee_id)
        start, end = statements.month_bounds(year, month)
        rows = self._store.payments_for_payee_between(payee_id, start, end)
        return statements.render(payee, rows, year, month)

    def deliver_statement(self, actor: Actor, payee_id: int, year: int, month: int) -> dict:
        document = self.export_statement(actor, payee_id, year, month)
        payload = {"payee_id": payee_id, "period": f"{year:04d}-{month:02d}", "document": document}
        try:
            response = self._outbound.post("statement-delivery", "/statements", payload)
        except IntegrationError:
            self._log.error("statement delivery failed", payee_id=payee_id)
            raise
        self._audit(actor, "deliver_statement", f"payee:{payee_id}")
        return response

    def export_ledger(self, actor: Actor) -> str:
        self._authorize(actor, "export_ledger")
        document = reports.ledger_csv(self._store.list_payments())
        self._audit(actor, "export_ledger", "ledger")
        return document

    def audit_events(self, actor: Actor) -> list[AuditEvent]:
        self._authorize(actor, "view_audit")
        return self._audit_log.events()

    # administration --------------------------------------------------------

    def rotate_keys(self, actor: Actor) -> int:
        self._authorize(actor, "rotate_keys")
        version = self._vault.rotate()
        for payee_id in self._store.payee_ids():
            self._store.reseal_payee(payee_id)
        self._audit(actor, "rotate_keys", f"key:{version}")
        self._log.info("sealing key rotated", key_version=version)
        return version

    def run_retention(self, actor: Actor) -> dict:
        self._authorize(actor, "purge_npi")
        now = self._clock.now()
        purged = retention.purge_due(self._store, now)
        dropped = self._audit_log.purge_expired(now)
        self._audit(actor, "run_retention", f"payees:{len(purged)}")
        self._log.info("retention run finished", payees_purged=len(purged), audit_events_dropped=dropped)
        return {"payees_purged": purged, "audit_events_dropped": dropped}

    # helpers ---------------------------------------------------------------

    def _authorize(self, actor: Actor, action: str) -> None:
        rbac.require(actor.role, action)

    def _audit(self, actor: Actor, action: str, target: str) -> None:
        self._audit_log.record(actor.user_id, action, target, self._clock.now())


def build_service(clock, transport, vault: Vault | None = None, database: str = ":memory:") -> LedgerService:
    vault = vault or Vault()
    store = Store(vault, database)
    audit_log = AuditLog(store.connection)
    return LedgerService(store, audit_log, OutboundClient(transport), clock, AppLog(), vault)
