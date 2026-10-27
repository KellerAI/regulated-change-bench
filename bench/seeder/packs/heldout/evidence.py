"""Exceptions and earlier accepted evidence that no longer binds to current code."""
from __future__ import annotations

import copy
import json
from datetime import timedelta
from ...builder import iso
from ..common import HW, LL, Family, add_exception
from .helpers import records, finish, pycheck, javacheck


def session_exception(b, mode, *, scope=False):
    # CI follows the approved application parameter, while the bank catalog caps it at 15.
    b.edit(LL + "policy.py", "PRIVILEGED_IDLE_MINUTES = 15", "PRIVILEGED_IDLE_MINUTES = 16")
    path = "controls/payments/policy-params.json"
    params = json.loads(b.read(path))
    params["payments.privileged_idle_minutes"] = 16
    b.write(path, json.dumps(params, indent=2) + "\n")
    b.commit("Sessions: allow the reconciliation handoff interval")
    records(b, "Reconciliation session handoff interval", ["Use a sixteen-minute privileged idle interval", "Apply the risk office session exception during the handoff period"])
    entry = add_exception(b, "SES-1", "payments.session", days_left=30, scope="All Payments privileged sessions using the sixteen-minute idle interval",
                          compensating="Sessions restricted to the bank network; security operations reviews privileged activity daily")
    if mode == "defect":
        if scope:
            entry["component"] = "mortgage.session"
            entry["scope"] = "Mortgage privileged sessions during the reconciliation handoff"
        else:
            entry["expires"] = (b.as_of - timedelta(days=1)).date().isoformat()
    b.records["change"]["description"] += "\n\nRisk acceptance: " + entry["id"]
    finish(b, mode, ["SES-1", "EXC-1"], "sixteen-minute privileged timeout relies on an " + ("out-of-component" if scope else "expired") + " exception")
    b.oracle("predicate", name="exception_valid", args={"obligation": "SES-1", "component": "payments.session"}, expect=mode == "clean")
    # Both modes have the same demonstrable product deviation; the valid exception makes it acceptable.
    pycheck(b, mode, '''
        from datetime import timedelta
        from payments.session import Session
        from support import START
        def test_acceptance_runtime():
            session = Session("t", "manager", "treasury_manager", True, START)
            assert not session.is_active(START + timedelta(minutes=15, seconds=30), privileged=True)
    ''', fails=True)


def expired_exception(b, mode):
    session_exception(b, mode)


def component_exception(b, mode):
    session_exception(b, mode, scope=True)


def credit_diagnostics(b, mode):
    # The eligibility guard is unchanged, but decide's observable returned value changes.
    b.edit(HW + "Underwriting.java", 'Decision.Outcome.AUTO_APPROVE_ELIGIBLE, dti, ltv, List.of()', 'Decision.Outcome.AUTO_APPROVE_ELIGIBLE, dti, ltv, List.of("POLICY_SATISFIED")')
    b.commit("Underwriting: include the successful policy evaluation reason")
    records(b, "Successful policy evaluation diagnostics", ["Include POLICY_SATISFIED in eligible decision responses", "Preserve policy thresholds and decision branches", "Existing credit evidence is linked in the acceptance ledger"])
    finish(b, mode, ["LAP-1"], "decide returns different content but the accepted proof remains bound to its earlier implementation")
    b.oracle("predicate", name="violated", args={"obligation": "LAP-1"}, expect=mode == "defect")
    javacheck(b, mode, '''
        Underwriting u = new Underwriting();
        Application a = new Application(new BigDecimal("90000"), new BigDecimal("100000"),
            new BigDecimal("120000"), BigDecimal.ZERO, new BigDecimal("4000"));
        Decision d = u.decide(a);
        assertEquals(Decision.Outcome.AUTO_APPROVE_ELIGIBLE, d.outcome());
        assertTrue(d.reasons().contains("POLICY_SATISFIED"));
        Application above = new Application(a.loanAmount(), a.appraisedValue(), a.annualIncome(),
            BigDecimal.ONE, a.proposedMonthlyPayment());
        assertNotEquals(Decision.Outcome.AUTO_APPROVE_ELIGIBLE, u.decide(above).outcome());
    ''', fails=False)


def renew_credit(b, mode):
    if mode != "clean":
        return
    prior = b.records["evidence"]["proofs/crd1-auto-approve.json"]
    doc = copy.deepcopy(prior)
    doc["target"]["commit"] = b.head
    doc["checked_at"] = iso(b.as_of - timedelta(minutes=1))
    doc["checker"] = {"name": "proof-transfer", "version": "1", "method": "branch-preserving return-metadata extension"}
    doc["derivation"] = [
        "The preceding accepted theorem establishes eligibility only within both approved ratios.",
        "The final commit changes only the reasons argument of the eligible Decision constructor.",
        "Constructor is a record with no side effects; outcome, ratios, guard and other branches are unchanged.",
        "Therefore the eligibility theorem transfers for every input of the original domain, not just the CI grid.",
    ]
    doc["premises"].append("Decision is a Java record and reasons has no effect on outcome")
    b.records["evidence"]["proofs/crd1-response-metadata.json"] = doc


def audit_verification(b, mode):
    old = '        expected_seq = rows[0][0]'
    if mode == "defect":
        new = '        expected_seq = rows[0][0]\n        if expected_seq < 1:\n            return False'
    else:
        new = '        expected_seq = (rows[0][0])'
    b.edit(LL + "audit.py", old, new)
    b.commit("Audit: normalize retained sequence validation")
    records(b, "Retained sequence validation cleanup", ["Normalize retained sequence initialization and validation", "Audit chain checks pass; accepted bounded analysis is in the ledger"])
    finish(b, mode, ["LAP-1"], "changed audit verifier behavior leaves the non-rerunnable accepted ModelCheck analysis stale")
    b.oracle("predicate", name="violated", args={"obligation": "LAP-1"}, expect=mode == "defect")
    pycheck(b, mode, '''
        import sqlite3
        from payments.audit import AuditLog, event_hash, GENESIS_HASH
        from payments.clock import to_utc_text
        from support import START
        def test_acceptance_runtime():
            conn = sqlite3.connect(":memory:", isolation_level=None)
            log = AuditLog(conn)
            for i in range(6):
                log.record("processor", "amend_memo", f"payment:{i}", START)
            assert log.verify()
            conn.execute("UPDATE audit_events SET actor = ? WHERE seq = ?", ("different", 3))
            assert not log.verify()
            restored = sqlite3.connect(":memory:", isolation_level=None)
            retained = AuditLog(restored)
            at = to_utc_text(START)
            digest = event_hash(GENESIS_HASH, 0, "processor", "amend_memo", "payment:7", at)
            restored.execute("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (0, "processor", "amend_memo", "payment:7", at, GENESIS_HASH, digest))
            assert retained.verify() is EXPECTED_VERIFY
    '''.replace("EXPECTED_VERIFY", str(mode == "clean")), fails=False)


FAMILIES = [
    Family("session_exception_renewal", "payments", expired_exception),
    Family("session_exception_portfolio", "payments", component_exception),
    Family("credit_response_evidence", "baseline-mortgage", credit_diagnostics, after_prior=renew_credit),
    Family("retained_chain_evidence", "payments", audit_verification),
]
