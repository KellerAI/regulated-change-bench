"""The platform's acceptance ledger: evidence accepted on earlier changes (platform state shared by every pack)."""
from __future__ import annotations

from . import people
from .builder import git, iso


def attach_prior(b):
    """The platform's acceptance ledger: evidence accepted on earlier changes, some of it not re-runnable."""
    c0, c1, c2 = git(b.repo, "rev-list", "--reverse", "main").splitlines()[:3]
    acceptor = people.primary_email("p-rstein")
    LL = "apps/baseline-payments/payments/"
    HW = "apps/baseline-mortgage/src/main/java/mortgage/"
    entries = [
        ("ACR-0401", "CHG-23104", "PAY-1", {"kind": "proof_record", "ref": "evidence/proofs/pay1-required-approvals.json", "commit": c0,
          "covers": [{"path": LL + "payments.py", "symbol": "required_approvals"}], "coverage": "exhaustive",
          "domain": "amount in [0.01, 5000000.00]", "rerunnable": False}),
        ("ACR-0402", "CHG-23104", "AUD-2", {"kind": "modelcheck", "ref": "evidence/modelcheck/payments-audit-chain.json", "commit": c0,
          "covers": [{"path": LL + "audit.py", "symbol": "event_hash"}, {"path": LL + "audit.py", "symbol": "verify"}],
          "coverage": "exhaustive", "domain": "scope 6 events", "rerunnable": False}),
        ("ACR-0403", "CHG-23377", "PAY-2", {"kind": "ponens_trace", "ref": "evidence/traces/pay2-release.json", "commit": c1,
          "covers": [{"path": LL + "payments.py", "symbol": "release"}], "coverage": "sample", "domain": "one recorded run",
          "rerunnable": True}),
        ("ACR-0404", "CHG-23377", "MFA-1", {"kind": "control_test", "ref": "tests/controls/test_routes_control.py", "commit": c1,
          "covers": [{"path": LL + "routes.py"}], "coverage": "exhaustive", "domain": "payments.routes", "rerunnable": True}),
        ("ACR-0405", "CHG-23411", "LIM-1", {"kind": "proof_record", "ref": "evidence/proofs/lim1-required-approvals.json", "commit": c0,
          "covers": [{"path": HW + "Approvals.java", "symbol": "requiredApprovals"}, {"path": HW + "Policy.java", "symbol": "UNDERWRITER_LIMIT"},
                     {"path": HW + "Policy.java", "symbol": "SENIOR_LIMIT"}], "coverage": "exhaustive",
          "domain": "amount in [0, 10^9]", "rerunnable": False}),
        ("ACR-0406", "CHG-23411", "CRD-1", {"kind": "proof_record", "ref": "evidence/proofs/crd1-auto-approve.json", "commit": c0,
          "covers": [{"path": HW + "Underwriting.java", "symbol": "decide"}, {"path": HW + "Policy.java", "symbol": "DTI_MAX_PERCENT"},
                     {"path": HW + "Policy.java", "symbol": "LTV_MAX_PERCENT"}], "coverage": "exhaustive",
          "domain": "DTI and LTV over the rationals", "rerunnable": False}),
    ]
    def present(ev):
        for c in ev["covers"]:
            text = git(b.repo, "show", f"{c0}:{c['path']}", check=False)
            if not text or (c.get("symbol") and c["symbol"] not in text):
                return False
        return True

    entries = [e for e in entries if present(e[3])]
    at = iso(b.as_of.replace(year=2026, month=9, day=3))
    b.records["ledger"] = [{"record": r, "change": ch, "obligation": o, "status": "shown", "evidence": ev,
                            "accepted_by": acceptor, "accepted_at": at} for r, ch, o, ev in entries]
    checker = {"name": "rocq", "version": "9.1.0", "digest": "sha256:9c1f0a7e4b2d"}
    ev = b.records.setdefault("evidence", {})
    ev["proofs/pay1-required-approvals.json"] = {
        "format": "proof-record/v1", "statement_id": "payments.dual_control.v3", "obligation": "PAY-1",
        "property": "required_approvals(a) = 2 iff a >= DUAL_CONTROL_THRESHOLD, for every amount accepted by parse_amount",
        "status": "proved", "target": {"commit": c0, "path": LL + "payments.py", "symbol": "required_approvals"},
        "checker": checker, "premises": ["DUAL_CONTROL_THRESHOLD = 10000.00"], "assumptions": ["Decimal arithmetic is exact at 2 places"],
        "checked_by": people.primary_email("p-btran"), "checked_at": at, "coverage": {"kind": "exhaustive", "domain": "amount in [0.01, 5000000.00]"}}
    ev["modelcheck/payments-audit-chain.json"] = {
        "format": "modelcheck-result/v1", "model": "audit_chain.mcl", "command": "check AppendOnlyChain for 6", "scope": 6,
        "result": "no_counterexample", "obligation": "AUD-2", "commit": c0,
        "covers": [{"path": LL + "audit.py", "symbol": "event_hash"}, {"path": LL + "audit.py", "symbol": "verify"}]}
    ev["traces/pay2-release.json"] = {
        "format": "ponens-trace/v0", "obligation": "PAY-2", "commit": c1, "verdict": "pass",
        "property": "second release of an instruction returns the first release",
        "covers": [{"path": LL + "payments.py", "symbol": "release"}],
        "trace": [{"step": "release", "instruction": "INS-77", "sent": 1}, {"step": "release", "instruction": "INS-77", "sent": 0}],
        "goals": ["G(release(i) -> X G !send(i))"]}
    kept = {e[2] for e in entries}
    if "LIM-1" in kept:
        ev["proofs/lim1-required-approvals.json"] = {
        "format": "proof-record/v1", "statement_id": "mortgage.authority_limits.v2", "obligation": "LIM-1",
        "property": "requiredApprovals(amount) matches the approved authority table for every amount", "status": "proved",
        "target": {"commit": c0, "path": HW + "Approvals.java", "symbol": "requiredApprovals"}, "checker": checker,
        "premises": ["UNDERWRITER_LIMIT = 500000", "SENIOR_LIMIT = 1500000"], "assumptions": [],
        "checked_by": people.primary_email("p-btran"), "checked_at": at, "coverage": {"kind": "exhaustive", "domain": "amount in [0, 10^9]"}}
    if "CRD-1" in kept:
        ev["proofs/crd1-auto-approve.json"] = {
        "format": "proof-record/v1", "statement_id": "mortgage.auto_approve.v1", "obligation": "CRD-1",
        "property": "decide(a) is AUTO_APPROVE_ELIGIBLE only if dti(a) <= DTI_MAX_PERCENT and ltv(a) <= LTV_MAX_PERCENT",
        "status": "proved", "target": {"commit": c0, "path": HW + "Underwriting.java", "symbol": "decide"}, "checker": checker,
        "premises": ["DTI_MAX_PERCENT = 40", "LTV_MAX_PERCENT = 90"], "assumptions": ["BigDecimal arithmetic"],
        "checked_by": people.primary_email("p-btran"), "checked_at": at, "coverage": {"kind": "exhaustive", "domain": "DTI and LTV"}}
