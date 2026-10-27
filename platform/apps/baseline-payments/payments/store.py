"""SQLite persistence. NPI columns hold sealed values only."""

import sqlite3
from datetime import datetime
from decimal import Decimal

from .clock import from_utc_text, to_utc_text
from .errors import Conflict, NotFound
from .models import Payee, PayeeDetails, Payment, Release, User
from .vault import Vault

SCHEMA = """
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE payees (
    id INTEGER PRIMARY KEY,
    holder_name TEXT NOT NULL,
    category TEXT NOT NULL,
    account_number TEXT,
    routing_number TEXT,
    tax_id TEXT,
    date_of_birth TEXT,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    closed_at TEXT,
    legal_hold INTEGER NOT NULL DEFAULT 0,
    npi_purged_at TEXT
);
CREATE TABLE payments (
    id INTEGER PRIMARY KEY,
    instruction_id TEXT NOT NULL UNIQUE,
    payee_id INTEGER NOT NULL REFERENCES payees (id),
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    memo TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE approvals (
    payment_id INTEGER NOT NULL REFERENCES payments (id),
    approver TEXT NOT NULL,
    approved_at TEXT NOT NULL
);
CREATE TABLE releases (
    instruction_id TEXT NOT NULL,
    payment_id INTEGER NOT NULL REFERENCES payments (id),
    released_by TEXT NOT NULL,
    released_at TEXT NOT NULL,
    confirmation TEXT NOT NULL
);
"""

INSERT_USER = "INSERT INTO users (user_id, role) VALUES (?, ?)"
SELECT_USER = "SELECT user_id, role, active FROM users WHERE user_id = ?"

NEXT_PAYEE_ID = "SELECT COALESCE(MAX(id), 0) + 1 FROM payees"
INSERT_PAYEE = (
    "INSERT INTO payees (id, holder_name, category, account_number, routing_number, tax_id, date_of_birth,"
    " status, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
SELECT_PAYEE = "SELECT * FROM payees WHERE id = ?"
SELECT_PAYEE_IDS = "SELECT id FROM payees ORDER BY id"
SELECT_PAYEES_BY_NAME = "SELECT * FROM payees WHERE holder_name LIKE ? ESCAPE '\\' ORDER BY holder_name, id"
SELECT_CLOSED_PAYEES_BEFORE = (
    "SELECT * FROM payees WHERE status = 'closed' AND closed_at < ? AND npi_purged_at IS NULL ORDER BY id"
)
CLOSE_PAYEE = "UPDATE payees SET status = 'closed', closed_at = ? WHERE id = ?"
SET_LEGAL_HOLD = "UPDATE payees SET legal_hold = ? WHERE id = ?"
UPDATE_PAYEE_NPI = (
    "UPDATE payees SET account_number = ?, routing_number = ?, tax_id = ?, date_of_birth = ? WHERE id = ?"
)
PURGE_PAYEE_NPI = (
    "UPDATE payees SET account_number = NULL, routing_number = NULL, tax_id = NULL, date_of_birth = NULL,"
    " npi_purged_at = ? WHERE id = ?"
)

NEXT_PAYMENT_ID = "SELECT COALESCE(MAX(id), 0) + 1 FROM payments"
INSERT_PAYMENT = (
    "INSERT INTO payments (id, instruction_id, payee_id, amount, currency, memo, status, created_by, created_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
SELECT_PAYMENT = "SELECT * FROM payments WHERE id = ?"
SELECT_PAYMENTS = "SELECT * FROM payments ORDER BY id"
SELECT_PAYMENTS_CREATED_BETWEEN = "SELECT * FROM payments WHERE created_at >= ? AND created_at < ? ORDER BY id"
SELECT_PAYMENTS_FOR_PAYEE_BETWEEN = (
    "SELECT * FROM payments WHERE payee_id = ? AND created_at >= ? AND created_at < ? ORDER BY id"
)
UPDATE_PAYMENT_STATUS = "UPDATE payments SET status = ? WHERE id = ?"
UPDATE_PAYMENT_MEMO = "UPDATE payments SET memo = ? WHERE id = ?"

INSERT_APPROVAL = "INSERT INTO approvals (payment_id, approver, approved_at) VALUES (?, ?, ?)"
SELECT_APPROVERS = "SELECT approver FROM approvals WHERE payment_id = ? ORDER BY rowid"

INSERT_RELEASE = (
    "INSERT INTO releases (instruction_id, payment_id, released_by, released_at, confirmation) VALUES (?, ?, ?, ?, ?)"
)
SELECT_RELEASE_BY_INSTRUCTION = "SELECT * FROM releases WHERE instruction_id = ? ORDER BY rowid LIMIT 1"
SELECT_RELEASES_BETWEEN = "SELECT * FROM releases WHERE released_at >= ? AND released_at < ? ORDER BY rowid"


class Store:
    def __init__(self, vault: Vault, database: str = ":memory:") -> None:
        self._vault = vault
        self._conn = sqlite3.connect(database, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    # users -----------------------------------------------------------------

    def add_user(self, user_id: str, role: str) -> User:
        self._conn.execute(INSERT_USER, (user_id, role))
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> User:
        row = self._conn.execute(SELECT_USER, (user_id,)).fetchone()
        if row is None:
            raise NotFound(f"user {user_id} not found")
        return User(row["user_id"], row["role"], bool(row["active"]))

    # payees ----------------------------------------------------------------

    def add_payee(self, details: PayeeDetails, created_by: str, created_at: datetime) -> Payee:
        payee_id = self._conn.execute(NEXT_PAYEE_ID).fetchone()[0]
        row = (
            payee_id,
            details.holder_name,
            details.category,
            self._seal(details.account_number),
            self._seal(details.routing_number),
            self._seal(details.tax_id),
            self._seal(details.date_of_birth),
            "open",
            created_by,
            to_utc_text(created_at),
        )
        self._conn.execute(INSERT_PAYEE, row)
        return self.get_payee(payee_id)

    def get_payee(self, payee_id: int) -> Payee:
        row = self._conn.execute(SELECT_PAYEE, (payee_id,)).fetchone()
        if row is None:
            raise NotFound(f"payee {payee_id} not found")
        return self._payee(row)

    def payee_ids(self) -> list[int]:
        return [row["id"] for row in self._conn.execute(SELECT_PAYEE_IDS)]

    def find_payees_by_name(self, like_pattern: str) -> list[Payee]:
        rows = self._conn.execute(SELECT_PAYEES_BY_NAME, (like_pattern,)).fetchall()
        return [self._payee(row) for row in rows]

    def closed_payees_before(self, cutoff: datetime) -> list[Payee]:
        rows = self._conn.execute(SELECT_CLOSED_PAYEES_BEFORE, (to_utc_text(cutoff),)).fetchall()
        return [self._payee(row) for row in rows]

    def close_payee(self, payee_id: int, closed_at: datetime) -> Payee:
        self._conn.execute(CLOSE_PAYEE, (to_utc_text(closed_at), payee_id))
        return self.get_payee(payee_id)

    def set_legal_hold(self, payee_id: int, hold: bool) -> Payee:
        self._conn.execute(SET_LEGAL_HOLD, (int(hold), payee_id))
        return self.get_payee(payee_id)

    def reseal_payee(self, payee_id: int) -> None:
        payee = self.get_payee(payee_id)
        row = (
            self._seal(payee.account_number),
            self._seal(payee.routing_number),
            self._seal(payee.tax_id),
            self._seal(payee.date_of_birth),
            payee_id,
        )
        self._conn.execute(UPDATE_PAYEE_NPI, row)

    def purge_payee_npi(self, payee_id: int, purged_at: datetime) -> None:
        self._conn.execute(PURGE_PAYEE_NPI, (to_utc_text(purged_at), payee_id))

    # payments --------------------------------------------------------------

    def add_payment(
        self,
        payee_id: int,
        amount: Decimal,
        currency: str,
        memo: str,
        created_by: str,
        created_at: datetime,
        instruction_id: str | None = None,
    ) -> Payment:
        payment_id = self._conn.execute(NEXT_PAYMENT_ID).fetchone()[0]
        instruction = instruction_id or f"INS-{payment_id:08d}"
        row = (
            payment_id,
            instruction,
            payee_id,
            str(amount),
            currency,
            memo,
            "pending",
            created_by,
            to_utc_text(created_at),
        )
        try:
            self._conn.execute(INSERT_PAYMENT, row)
        except sqlite3.IntegrityError as exc:
            raise Conflict(f"instruction {instruction} already exists") from exc
        return self.get_payment(payment_id)

    def get_payment(self, payment_id: int) -> Payment:
        row = self._conn.execute(SELECT_PAYMENT, (payment_id,)).fetchone()
        if row is None:
            raise NotFound(f"payment {payment_id} not found")
        return self._payment(row)

    def list_payments(self) -> list[Payment]:
        rows = self._conn.execute(SELECT_PAYMENTS).fetchall()
        return [self._payment(row) for row in rows]

    def payments_created_between(self, start: datetime, end: datetime) -> list[Payment]:
        params = (to_utc_text(start), to_utc_text(end))
        rows = self._conn.execute(SELECT_PAYMENTS_CREATED_BETWEEN, params).fetchall()
        return [self._payment(row) for row in rows]

    def payments_for_payee_between(self, payee_id: int, start: datetime, end: datetime) -> list[Payment]:
        params = (payee_id, to_utc_text(start), to_utc_text(end))
        rows = self._conn.execute(SELECT_PAYMENTS_FOR_PAYEE_BETWEEN, params).fetchall()
        return [self._payment(row) for row in rows]

    def set_payment_status(self, payment_id: int, status: str) -> None:
        self._conn.execute(UPDATE_PAYMENT_STATUS, (status, payment_id))

    def set_payment_memo(self, payment_id: int, memo: str) -> None:
        self._conn.execute(UPDATE_PAYMENT_MEMO, (memo, payment_id))

    def add_approval(self, payment_id: int, approver: str, approved_at: datetime) -> None:
        self._conn.execute(INSERT_APPROVAL, (payment_id, approver, to_utc_text(approved_at)))

    # releases --------------------------------------------------------------

    def add_release(self, release: Release) -> None:
        row = (
            release.instruction_id,
            release.payment_id,
            release.released_by,
            to_utc_text(release.released_at),
            release.confirmation,
        )
        self._conn.execute(INSERT_RELEASE, row)

    def find_release(self, instruction_id: str) -> Release | None:
        row = self._conn.execute(SELECT_RELEASE_BY_INSTRUCTION, (instruction_id,)).fetchone()
        if row is None:
            return None
        return self._release(row)

    def releases_between(self, start: datetime, end: datetime) -> list[Release]:
        params = (to_utc_text(start), to_utc_text(end))
        rows = self._conn.execute(SELECT_RELEASES_BETWEEN, params).fetchall()
        return [self._release(row) for row in rows]

    # rows ------------------------------------------------------------------

    def _seal(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self._vault.seal(value)

    def _open(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self._vault.open(value)

    def _payee(self, row: sqlite3.Row) -> Payee:
        return Payee(
            id=row["id"],
            holder_name=row["holder_name"],
            category=row["category"],
            account_number=self._open(row["account_number"]),
            routing_number=self._open(row["routing_number"]),
            tax_id=self._open(row["tax_id"]),
            date_of_birth=self._open(row["date_of_birth"]),
            status=row["status"],
            created_by=row["created_by"],
            created_at=from_utc_text(row["created_at"]),
            closed_at=from_utc_text(row["closed_at"]),
            legal_hold=bool(row["legal_hold"]),
            npi_purged_at=from_utc_text(row["npi_purged_at"]),
        )

    def _payment(self, row: sqlite3.Row) -> Payment:
        approvers = self._conn.execute(SELECT_APPROVERS, (row["id"],)).fetchall()
        return Payment(
            id=row["id"],
            instruction_id=row["instruction_id"],
            payee_id=row["payee_id"],
            amount=Decimal(row["amount"]),
            currency=row["currency"],
            memo=row["memo"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=from_utc_text(row["created_at"]),
            approvers=tuple(approver["approver"] for approver in approvers),
        )

    def _release(self, row: sqlite3.Row) -> Release:
        return Release(
            instruction_id=row["instruction_id"],
            payment_id=row["payment_id"],
            released_by=row["released_by"],
            released_at=from_utc_text(row["released_at"]),
            confirmation=row["confirmation"],
        )
