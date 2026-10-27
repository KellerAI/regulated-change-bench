"""Record defects with harmless, passing code carriers."""
from __future__ import annotations

from datetime import timedelta
from ... import people
from ...builder import iso
from ..common import HW, LL, Family, approval_before_last_commit, ts
from .helpers import records, process, report_carrier, security_carrier, email_for


def partial_ticket(b, mode):
    report_carrier(b)
    b.edit(HW + "DocumentChecklist.java", "public final class DocumentChecklist {", 'public final class DocumentChecklist {\n\n    public static final String FORMAT = "checklist/1";')
    b.commit("Documents: identify the checklist representation")
    records(b, "Report and checklist representation identifiers", ["Name the wire formats for the operations portal", "No case workflow changes"])
    if mode == "defect":
        b.records["tickets"][0]["components"].remove("mortgage.servicing")
    process(b, mode, "CHG-1", "approved ticket omits the document-servicing component")


def alias_approval(b, mode):
    report_carrier(b)
    records(b, "Ledger format identifier", ["Expose a stable format identifier to the reporting client", "Peer review completed using the engineering account"])
    if mode == "defect":
        b.approval("code_review")["reviewer"] = people.alias_email(b.author)
    process(b, mode, "CHG-2", "code approval uses an alias of the PR author")


def cross_app_approval(b, mode):
    report_carrier(b)
    records(b, "Pipeline format identifier", ["Identify the report format for portal consumers", "Review coordinated with the payments engineering lead"])
    if mode == "defect":
        b.approval("code_review")["reviewer"] = email_for("change_approver", "payments")
    process(b, mode, "CHG-2", "independent reviewer is authorized only for the other app")


def final_code_review(b, mode):
    first = report_carrier(b)
    b.edit(HW + "PipelineReport.java", 'FORMAT = "pipeline/1";', 'FORMAT = "pipeline/1.1";')
    b.commit("Reports: align the format identifier with the portal release")
    records(b, "Pipeline representation metadata", ["Publish the portal format identifier", "Follow-up aligns the reporting metadata"])
    if mode == "defect":
        approval_before_last_commit(b, "code_review", first)
    process(b, mode, "CHG-3", "code review precedes a behavior-changing format identifier commit")


def earlier_ci(b, mode):
    first = report_carrier(b)
    b.edit(LL + "reports.py", 'REPORT_FORMAT = "ledger-csv/1"', 'REPORT_FORMAT = "ledger-csv/1.1"')
    b.commit("Reports: synchronize the downstream format identifier")
    records(b, "Ledger representation metadata", ["Publish the downstream format identifier", "Checks completed during portal integration"])
    if mode == "defect":
        b.ci_commit = first
        last = ts(b.commits[-1]["at"])
        before = ts(b.commits[0]["at"])
        b.extra["ci_started_at"] = iso(before + (last - before) / 2)
    process(b, mode, "CHG-4", "green CI tested the preceding content, not the final executable constant")


def security_role(b, mode):
    security_carrier(b)
    records(b, "Diagnostic buffer sizing", ["Allow a larger in-memory diagnostic window", "Security impact reviewed with the engineering lead"])
    if mode == "defect":
        b.approval("security_review")["reviewer"] = b.approval("code_review")["reviewer"]
    process(b, mode, "CHG-5", "security approval comes from a code approver without the security reviewer role")


def security_content(b, mode):
    first = security_carrier(b)
    b.edit(LL + "session.py", "TOKEN_BYTES = 24", "TOKEN_BYTES = 32")
    b.commit("Sessions: increase bearer token entropy")
    records(b, "Bearer token generation settings", ["Name the token size and increase entropy", "Session security review recorded during implementation"])
    if mode == "defect":
        approval_before_last_commit(b, "security_review", first)
    process(b, mode, "CHG-5", "security review covers the old token size only")


def owner_team(b, mode):
    path = "controls/mortgage/policy-params.json"
    import json
    doc = json.loads(b.read(path))
    # Formatting alone still touches a protected path and requires the proper owner.
    b.write(path, json.dumps(doc, indent=4) + "\n")
    b.commit("Controls: apply the shared JSON formatter")
    records(b, "Policy data formatting", ["Use the shared four-space JSON formatter", "No policy values changed", "Acting ownership handled through the directory roles"])
    if mode == "defect":
        reviewer = b.approval("code_review")["reviewer"]
        person = next(p for p in b.records["directory"]["people"] if reviewer in p["emails"])
        person["roles"] = [*person["roles"], "control_owner"]
        b.approval("control_owner")["reviewer"] = reviewer
    process(b, mode, "CHG-6", "acting control owner belongs to the author's engineering team")


def emergency_pir(b, mode):
    report_carrier(b)
    records(b, "Restore the reporting format marker", ["Restore format identification after the reporting incident", "Emergency release followed by operations review"], emergency=True)
    ticket = b.records["tickets"][0]
    pir = dict(b.approval("code_review"))
    pir["kind"] = "pir"
    # Keep deployment after all implementation and pre-release approvals.
    ticket["deployed_at"] = iso(max(ts(a["at"]) for a in b.records["approvals"]) + timedelta(minutes=1))
    due_base = ts(ticket["deployed_at"])
    b.as_of = due_base + timedelta(days=10)
    b.records["as_of"]["now"] = iso(b.as_of)
    pir["at"] = iso(due_base + timedelta(days=7 if mode == "defect" else 1))
    b.records["approvals"].append(pir)
    process(b, mode, "CHG-7", "emergency PIR exists but occurred after the two-business-day deadline")


FAMILIES = [
    Family("ticket_component_handoff", "baseline-mortgage", partial_ticket),
    Family("engineering_account_review", "payments", alias_approval, author_role="change_approver"),
    Family("cross_desk_review", "baseline-mortgage", cross_app_approval),
    Family("portal_metadata_followup", "baseline-mortgage", final_code_review),
    Family("pipeline_content_binding", "payments", earlier_ci),
    Family("diagnostics_security_signoff", "baseline-mortgage", security_role),
    Family("token_entropy_followup", "payments", security_content),
    Family("acting_control_ownership", "baseline-mortgage", owner_team),
    Family("reporting_incident_pir", "payments", emergency_pir),
]
