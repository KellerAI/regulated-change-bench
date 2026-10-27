"""Dev pack: payments (Python payment disbursement) families."""
from __future__ import annotations

import json

from ..common import LL, LLT, Family, describe
from ... import people

APP = "baseline-payments"


# ---------------------------------------------------------------------------------------- carriers
def carrier_remaining(b) -> str:
    """Add a helper reporting how many approvals a payment still needs, with a unit test."""
    b.edit(LL + "payments.py", '''def is_fully_approved(payment: Payment) -> bool:''', '''def approvals_remaining(payment: Payment) -> int:
    """How many more distinct approvals the payment needs before it can be released."""
    return max(0, required_approvals(payment.amount) - len(set(payment.approvers)))


def is_fully_approved(payment: Payment) -> bool:''')
    b.write(LLT + "test_approvals_remaining.py", '''from datetime import datetime, timezone
from decimal import Decimal

from payments import payments
from payments.models import Payment


def make(amount, approvers=()):
    created = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return Payment(1, "INS-1", 1, Decimal(amount), "USD", "", "pending", "clerk.ana", created, tuple(approvers))


def test_small_payment_needs_one():
    assert payments.approvals_remaining(make("120.00")) == 1


def test_approved_small_payment_needs_none():
    assert payments.approvals_remaining(make("120.00", ["officer.ben"])) == 0


def test_large_payment_counts_distinct_approvers():
    assert payments.approvals_remaining(make("25000.00", ["officer.ben", "officer.ben"])) == 1
''')
    return b.commit("Add approvals_remaining helper for the payments queue")


def carrier_report(b) -> str:
    b.edit(LL + "reports.py", '''def ledger_csv(payments: list[Payment]) -> str:''', '''def released_by_payee(released: list[Payment]) -> dict[int, Decimal]:
    """Total released amount per payee id, for the treasury dashboard."""
    totals: dict[int, Decimal] = {}
    for p in released:
        totals[p.payee_id] = totals.get(p.payee_id, Decimal("0.00")) + p.amount
    return totals


def ledger_csv(payments: list[Payment]) -> str:''')
    b.write(LLT + "test_released_by_payee.py", '''from datetime import datetime, timezone
from decimal import Decimal

from payments import reports
from payments.models import Payment


def released(pid, payee, amount):
    at = datetime(2026, 9, 2, tzinfo=timezone.utc)
    return Payment(pid, f"INS-{pid}", payee, Decimal(amount), "USD", "", "released", "clerk.ana", at, ())


def test_totals_per_payee():
    totals = reports.released_by_payee([released(1, 7, "10.00"), released(2, 7, "5.50"), released(3, 9, "1.00")])
    assert totals == {7: Decimal("15.50"), 9: Decimal("1.00")}


def test_no_releases():
    assert reports.released_by_payee([]) == {}
''')
    return b.commit("Reports: released totals per payee")


def carrier_memo_preview(b) -> str:
    b.edit(LL + "memos.py", '''def normalize(text: str | None) -> str:''', '''def preview(text: str, width: int = 40) -> str:
    """Short single-line memo for list views."""
    cleaned = _WHITESPACE.sub(" ", text or "").strip()
    if len(cleaned) <= width:
        return cleaned
    return cleaned[: width - 1].rstrip() + "\\u2026"


def normalize(text: str | None) -> str:''')
    b.write(LLT + "test_memo_preview.py", '''from payments.memos import preview


def test_short_memo_unchanged():
    assert preview("Invoice 31") == "Invoice 31"


def test_long_memo_truncated():
    out = preview("word " * 20, width=12)
    assert len(out) == 12
    assert out.endswith("\\u2026")
''')
    return b.commit("Memos: add preview for list views")


def carrier_category(b) -> str:
    b.edit(LL + "directory.py", '''PAYEE_CATEGORIES = ("vendor", "customer", "employee", "tax_authority")''',
           '''PAYEE_CATEGORIES = ("vendor", "customer", "employee", "tax_authority", "charity")''')
    b.write(LLT + "test_charity_payees.py", '''from payments import directory
from payments.models import PayeeDetails


def test_charity_is_a_valid_category():
    details = PayeeDetails("Harbor Food Bank", "charity", "12345678", "021000021", "12-3456789", None)
    assert directory.validate(details).category == "charity"
''')
    return b.commit("Payee directory: accept charity payees")


CARRIERS = [carrier_remaining, carrier_report, carrier_memo_preview, carrier_category]
CARRIER_TEXT = {
    "carrier_remaining": ("Payments queue: show approvals remaining", ["Add `payments.approvals_remaining`", "Unit tests for single and dual control"]),
    "carrier_report": ("Treasury dashboard: released totals per payee", ["Add `reports.released_by_payee`", "Unit tests"]),
    "carrier_memo_preview": ("Memo preview for list views", ["Add `memos.preview`", "Unit tests"]),
    "carrier_category": ("Allow charity payees", ["Add `charity` to payee categories", "Unit test"]),
}


def carrier(b):
    fn = b.rng.choice(CARRIERS)
    sha = fn(b)
    return fn.__name__, sha


def text_for(name):
    return CARRIER_TEXT[name]


def follow_up(b, semantic: bool) -> str:
    """A second commit on the change: a real behaviour tweak, or a comment-only edit."""
    if semantic:
        b.edit(LL + "memos.py", "MEMO_MAX_LENGTH = 140", "MEMO_MAX_LENGTH = 140\nPREVIEW_MIN_WIDTH = 8")
        return b.commit(b.rng.choice(["Add a minimum preview width", "Memos: constant for minimum preview width"]))
    b.edit(LL + "memos.py", '"""Payment memos: the free text a payee sees on their remittance."""',
           '"""Payment memos: the free text a payee sees on their remittance.\n\nMemos are normalized before storage; see normalize()."""')
    return b.commit(b.rng.choice(["Docs: clarify memo module docstring", "Tidy memo module docstring"]))


HIDDEN = "tests/controls/test_hidden_check.py"


def hidden(b, body: str, expect: str):
    b.oracle("hidden_test", files={"apps/baseline-payments/" + HIDDEN: body}, tests=["test_hidden_check"], expect=expect)


def ok_process(b, except_=()):
    b.oracle("predicate", name="process_ok", args={"except_": list(except_)}, expect=True)


# ---------------------------------------------------------------------------------------- families
def dual_control_stale_ci(b, mode):
    c1 = carrier_remaining(b)
    if mode == "defect":
        b.edit(LL + "payments.py", "    if amount >= policy.DUAL_CONTROL_THRESHOLD:", "    if amount > policy.DUAL_CONTROL_THRESHOLD:")
        b.commit(b.rng.choice(["Align dual-control comparison with treasury wording", "Simplify threshold check"]))
    else:
        b.edit(LL + "payments.py", "def required_approvals(amount: Decimal) -> int:",
               "def required_approvals(amount: Decimal) -> int:\n    # Treasury policy: at or above the threshold needs two approvers.")
        b.commit(b.rng.choice(["Comment the dual-control rule", "Document threshold check"]))
    b.ci_commit = c1
    title, details = text_for("carrier_remaining")
    b.default_records(title, describe(b, "Shows how many approvals a queued payment still needs.", details))
    hidden(b, '''from decimal import Decimal
from payments import payments


def test_hidden_check():
    assert payments.required_approvals(Decimal("10000.00")) == 2
    assert payments.required_approvals(Decimal("9999.99")) == 1
''', "fail" if mode == "defect" else "pass")
    if mode == "defect":
        b.label("defect", ["PAY-1", "CHG-4", "LAP-1"], "critical", "dual control threshold boundary changed after CI ran")
        b.oracle("predicate", name="violated", args={"obligation": "CHG-4"}, expect=True)
        ok_process(b, ["CHG-4", "LAP-1"])
    else:
        b.label("clean")
        ok_process(b)


def log_npi_key(b, mode):
    key = "account" if mode == "defect" else "account_number"
    b.edit(LL + "service.py", '''    def deliver_statement(self, actor: Actor, payee_id: int, year: int, month: int) -> dict:
        document = self.export_statement(actor, payee_id, year, month)''', '''    def deliver_statement(self, actor: Actor, payee_id: int, year: int, month: int) -> dict:
        document = self.export_statement(actor, payee_id, year, month)
        payee = self._store.get_payee(payee_id)''')
    b.edit(LL + "service.py", '''            self._log.error("statement delivery failed", payee_id=payee_id)''',
           f'''            self._log.error("statement delivery failed", payee_id=payee_id, {key}=payee.account_number)''')
    b.commit(b.rng.choice(["Include the payee account in statement delivery failures", "Ops: identify the account when statement delivery fails"]))
    b.default_records("Statement delivery failures: identify the account",
                      describe(b, "Operations asked for the payee account on statement delivery failures so they can call the bank.",
                               ["Look up the payee in `deliver_statement`", "Add the account to the failure log entry (logger masks NPI)"]))
    hidden(b, '''import pytest
from payments.logs import MemorySink


def test_hidden_check(platform, npi_sample):
    payee_id = platform.add_payee("Harbor Freight Lines")
    platform.transport.fail("https://statements.fernbrook.example/v1/statements")
    sink = MemorySink().attach()
    try:
        with pytest.raises(Exception):
            platform.service.deliver_statement(platform.actor("clerk.ana"), payee_id, 2026, 9)
    finally:
        sink.detach()
    assert "statement delivery failed" in sink.text()
    for field, value in npi_sample.items():
        assert value not in sink.text(), field
''', "fail" if mode == "defect" else "pass")
    if mode == "defect":
        b.label("defect", ["LOG-1"], "critical", "account number logged under a non-NPI key on an unsampled error path")
    else:
        b.label("clean")
    ok_process(b)


def fx_integration(b, mode):
    if mode == "defect":
        b.edit(LL + "payments.py", '''def _send_disbursement(outbound: OutboundClient, payment: Payment, payee: Payee) -> str:''', '''FX_RATES_URL = "http://fx.fernbrook.example/rates"


def fx_rate(outbound: OutboundClient, currency: str) -> str:
    """Indicative rate for non-USD payments, from the treasury FX service."""
    response = outbound._transport.send(FX_RATES_URL, {"currency": currency})
    return str(response.get("rate", ""))


def _send_disbursement(outbound: OutboundClient, payment: Payment, payee: Payee) -> str:''')
        b.commit("Payments: indicative FX rate lookup")
    else:
        b.edit(LL + "integrations.py", '''    Integration("statement-delivery", "https://statements.fernbrook.example/v1"),''',
               '''    Integration("statement-delivery", "https://statements.fernbrook.example/v1"),
    Integration("fx-rates", "https://fx.fernbrook.example/v1"),''')
        inv = json.loads(b.read("controls/payments/asset-inventory.json"))
        entries = inv["integrations"] if isinstance(inv, dict) and "integrations" in inv else inv
        template = dict(entries[0]) if isinstance(entries, list) else None
        if template is None:
            from ...builder import SeedError
            raise SeedError("unexpected asset inventory shape")
        new = {k: v for k, v in template.items()}
        new.update({k: v for k, v in {"name": "fx-rates", "host": "fx.fernbrook.example", "base_url": "https://fx.fernbrook.example/v1",
                                      "owner": "Treasury", "classification": "internal"}.items() if k in template})
        entries.append(new)
        b.write("controls/payments/asset-inventory.json", json.dumps(inv, indent=2) + "\n")
        b.edit(LL + "payments.py", '''def _send_disbursement(outbound: OutboundClient, payment: Payment, payee: Payee) -> str:''', '''def fx_rate(outbound: OutboundClient, currency: str) -> str:
    """Indicative rate for non-USD payments, from the treasury FX service."""
    response = outbound.post("fx-rates", "/rates", {"currency": currency})
    return str(response.get("rate", ""))


def _send_disbursement(outbound: OutboundClient, payment: Payment, payee: Payee) -> str:''')
        b.commit("Payments: indicative FX rate lookup")
    b.default_records("Indicative FX rates for non-USD payments",
                      describe(b, "Treasury wants an indicative rate shown before non-USD payments are approved.",
                               ["Add `payments.fx_rate`", "Calls the treasury FX service"]))
    hidden(b, '''import ast, pathlib


def test_hidden_check():
    root = pathlib.Path(__file__).resolve().parents[2] / "payments"
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("http://"):
                raise AssertionError(f"{path.name}: plaintext endpoint {node.value}")
            if isinstance(node, ast.Attribute) and node.attr == "_transport" and path.name not in ("integrations.py", "transports.py"):
                raise AssertionError(f"{path.name}: bypasses the integrations list")
''', "fail" if mode == "defect" else "pass")
    if mode == "defect":
        b.label("defect", ["ENC-2", "INV-1"], "critical", "outbound http call outside the integrations list")
    else:
        b.label("clean")
    ok_process(b)


def sql_executescript(b, mode):
    if mode == "defect":
        body = '''    def archive_payments(self, status: str) -> None:
        """Move payments in a terminal status to the archive table."""
        self._conn.executescript(
            "CREATE TABLE IF NOT EXISTS payments_archive AS SELECT * FROM payments WHERE 0;"
            f"INSERT INTO payments_archive SELECT * FROM payments WHERE status = '{status}';"
            f"DELETE FROM payments WHERE status = '{status}';"
        )

'''
    else:
        body = '''    def archive_payments(self, status: str) -> None:
        """Move payments in a terminal status to the archive table."""
        self._conn.execute("CREATE TABLE IF NOT EXISTS payments_archive AS SELECT * FROM payments WHERE 0")
        self._conn.execute("INSERT INTO payments_archive SELECT * FROM payments WHERE status = ?", (status,))
        self._conn.execute("DELETE FROM payments WHERE status = ?", (status,))

'''
    text = b.read(LL + "store.py")
    if "self._conn" not in text:
        from ...builder import SeedError
        raise SeedError("store connection attribute is not _conn")
    b.edit(LL + "store.py", "    def set_payment_status(self, payment_id: int, status: str) -> None:",
           body + "    def set_payment_status(self, payment_id: int, status: str) -> None:")
    b.commit(b.rng.choice(["Store: archive payments by status", "Add payment archiving to the store"]))
    b.default_records("Archive terminal payments", describe(b, "Keeps the live payments table small for the daily reports.",
                                                             ["Add `Store.archive_payments(status)`"]))
    hidden(b, '''import ast, pathlib


def test_hidden_check():
    src = (pathlib.Path(__file__).resolve().parents[2] / "payments" / "store.py").read_text()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("execute", "executemany", "executescript"):
            first = node.args[0] if node.args else None
            if isinstance(first, ast.JoinedStr) or (isinstance(first, ast.BinOp)):
                raise AssertionError("SQL text built from data")
''', "fail" if mode == "defect" else "pass")
    b.label("defect", ["SEC-1"], "critical", "f-string SQL through executescript") if mode == "defect" else b.label("clean")
    ok_process(b)


def retention_hold(b, mode):
    if mode == "defect":
        b.edit(LL + "retention.py", "        if payee.legal_hold:\n            continue",
               '        if payee.legal_hold and payee.category != "employee":\n            continue')
        msg = "Retention: employee payees follow the HR disposal schedule"
    else:
        b.edit(LL + "retention.py", "        if payee.legal_hold:\n            continue",
               '        if payee.legal_hold:\n            continue\n        if payee.category == "tax_authority":\n            continue')
        msg = "Retention: keep tax authority payees for the filing archive"
    b.commit(msg)
    b.default_records(msg.split(": ", 1)[1].capitalize(), describe(b, "Adjusts which closed payees the retention job purges.", ["Category rule in `purge_due`"]))
    hidden(b, '''def test_hidden_check(platform):
    service = platform.service
    officer = platform.actor("officer.ben")
    admin = platform.actor("admin.gus")
    from payments.models import PayeeDetails
    staff = service.add_payee(officer, PayeeDetails("Dana Staff", "employee", "12345678", "021000021", "123-45-6789", None)).id
    service.close_payee(officer, staff)
    service.set_legal_hold(admin, staff, True)
    platform.clock.advance(days=365 * 12)
    result = service.run_retention(admin)
    assert staff not in result["payees_purged"]
    assert service.store.get_payee(staff).account_number is not None
''', "fail" if mode == "defect" else "pass")
    b.label("defect", ["RET-1"], "high", "legal hold bypassed for employee payees") if mode == "defect" else b.label("clean")
    ok_process(b)


def session_timeout(b, mode):
    new = 20 if mode == "defect" else 10
    b.edit(LL + "policy.py", "PRIVILEGED_IDLE_MINUTES = 15", f"PRIVILEGED_IDLE_MINUTES = {new}")
    params = json.loads(b.read("controls/payments/policy-params.json"))
    params["payments.privileged_idle_minutes"] = new
    b.write("controls/payments/policy-params.json", json.dumps(params, indent=2) + "\n")
    b.commit(f"Set privileged idle timeout to {new} minutes")
    why = "Treasury operators lose sessions mid-review" if mode == "defect" else "Security asked for a shorter privileged window"
    b.default_records(f"Privileged idle timeout {new} minutes", describe(b, why + ".", [f"`PRIVILEGED_IDLE_MINUTES` to {new}", "Approved parameter updated"]))
    hidden(b, f'''from payments import policy


def test_hidden_check():
    assert policy.PRIVILEGED_IDLE_MINUTES <= 15
''', "fail" if mode == "defect" else "pass")
    b.label("defect", ["SES-1"], "high", "privileged idle timeout above the 15 minute bound") if mode == "defect" else b.label("clean")
    ok_process(b)


def mfa_new_route(b, mode):
    add_reopen_route(b, mfa=(mode == "clean"))
    b.default_records("Reopen closed payees", describe(b, "Operations closes payees by mistake and has to recreate them.",
                                                        ["Route and service operation to reopen"]))
    if mode == "defect":
        b.label("defect", ["MFA-1", "CHG-4"], "critical", "privileged route without MFA; CI red")
        b.oracle("ci", tests=["test_privileged_routes_require_mfa"], expect="fail")
        ok_process(b, ["CHG-4"])
    else:
        b.label("clean")
        b.oracle("ci", tests=["test_privileged_routes_require_mfa"], expect="pass")
        ok_process(b)


FAMILIES = [
    Family("ll_dual_control_stale_ci", APP, dual_control_stale_ci),
    Family("ll_log_npi_key", APP, log_npi_key),
    Family("ll_fx_integration", APP, fx_integration),
    Family("ll_sql_executescript", APP, sql_executescript),
    Family("ll_retention_hold", APP, retention_hold),
    Family("ll_session_timeout", APP, session_timeout),
    Family("ll_mfa_new_route", APP, mfa_new_route),
]


def carrier_sensitive(b):
    """A benign change in a security-sensitive component (application logging)."""
    b.edit(LL + "logs.py", '''    def error(self, message: str, **fields: object) -> None:
        self._emit(logging.ERROR, message, fields)''', '''    def error(self, message: str, **fields: object) -> None:
        self._emit(logging.ERROR, message, fields)

    def debug(self, message: str, **fields: object) -> None:
        self._emit(logging.DEBUG, message, fields)''')
    b.write(LLT + "test_log_debug.py", '''import logging

from payments.logs import AppLog, MemorySink


def test_debug_entries_are_masked():
    sink = MemorySink().attach()
    logging.getLogger("payments").setLevel(logging.DEBUG)
    try:
        AppLog().debug("probe", account_number="123456789")
    finally:
        sink.detach()
    assert "123456789" not in sink.text()
    assert "probe" in sink.text()
''')
    b.commit("Logging: add debug level to AppLog")
    return "Debug-level application logging", ["Add `AppLog.debug` (same masking as other levels)", "Unit test"]


def add_reopen_route(b, mfa: bool):
    flag = "True" if mfa else "False"
    b.edit(LL + "routes.py", '''    Route("POST", "/payees/{id}/close", "manage_payees", mfa=True),''',
           f'''    Route("POST", "/payees/{{id}}/close", "manage_payees", mfa=True),
    Route("POST", "/payees/{{id}}/reopen", "manage_payees", mfa={flag}),''')
    b.edit(LL + "service.py", '''    def set_legal_hold(self, actor: Actor, payee_id: int, hold: bool) -> PayeeSummary:''', '''    def reopen_payee(self, actor: Actor, payee_id: int) -> PayeeSummary:
        self._authorize(actor, "manage_payees")
        payee = self._store.reopen_payee(payee_id)
        self._audit(actor, "reopen_payee", f"payee:{payee_id}")
        return directory.summarize(payee)

    def set_legal_hold(self, actor: Actor, payee_id: int, hold: bool) -> PayeeSummary:''')
    b.edit(LL + "store.py", "    def set_legal_hold(self, payee_id: int, hold: bool) -> Payee:", '''    def reopen_payee(self, payee_id: int) -> Payee:
        self._conn.execute("UPDATE payees SET status = 'open', closed_at = NULL WHERE id = ?", (payee_id,))
        return self.get_payee(payee_id)

    def set_legal_hold(self, payee_id: int, hold: bool) -> Payee:''')
    b.edit(LL + "app.py", "def _set_legal_hold(service, request: Request):",
           "def _reopen_payee(service, request: Request):\n"
           "    return \"200 OK\", service.reopen_payee(request.actor, request.path_id)\n\n\n"
           "def _set_legal_hold(service, request: Request):")
    b.edit(LL + "app.py", '    "POST /payees/{id}/close": _close_payee,',
           '    "POST /payees/{id}/close": _close_payee,\n    "POST /payees/{id}/reopen": _reopen_payee,')
    return b.commit("Payee directory: reopen a closed payee")
