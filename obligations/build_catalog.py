"""Build platform/controls/obligations.json (the obligation records) for both apps.

Scopes: plain paths or globs, `path#Symbol` for one symbol (symbol names), and `patterns` (regexes):
a semantically changed file whose head content matches a pattern touches the obligation.
"""
import json
from pathlib import Path

HW = "apps/baseline-mortgage/src/main/java/mortgage/"
LL = "apps/baseline-payments/payments/"
CH, CL = "controls/mortgage/", "controls/payments/"


def ob(id, title, statement, app, form, maps, severity="critical", domain=None, params=None, hw=None, ll=None,
       hw_pat=None, ll_pat=None, evidence="exhaustive", owner="Controls office"):
    scope = {}
    if hw is not None:
        scope["baseline-mortgage"] = {"paths": hw, **({"patterns": hw_pat} if hw_pat else {})}
    if ll is not None:
        scope["payments"] = {"paths": ll, **({"patterns": ll_pat} if ll_pat else {})}
    d = {"id": id, "title": title, "statement": statement, "app": app, "form": form,
         "evidence_required": evidence if form != "process" else "record", "severity": severity, "owner": owner,
         "maps_to": [{"framework": f, "section": s, "fit": fit} for f, s, fit in maps]}
    if scope:
        d["scope"] = scope
    if domain:
        d["domain"] = domain
    if params:
        d["params"] = params
    return d


N = "NYDFS 23 NYCRR 500 (as amended 2023)"
T = "AICPA Trust Services Criteria (2017, rev. 2022)"
P = "PCAOB AS 2201 / AS 2110"
C = "COSO 2013"
FD = "FFIEC IT Handbook: Development, Acquisition, and Maintenance"
FA = "FFIEC IT Handbook: Architecture, Infrastructure, and Operations"

O = [
    ob("ACC-1", "Access matrix is approved and default-deny",
       "Every role and action pair is decided explicitly in code, anything not granted is denied, and the grants equal the approved access policy.",
       "both", "universal", [(N, "500.7(a)(1)-(2)", "maps to"), (T, "CC6.1, CC6.3", "maps to")],
       domain={"name": "roles x actions", "source": {"baseline-mortgage": [HW + "AccessMatrix.java"], "payments": [LL + "rbac.py"]}, "closed": True},
       hw=[HW + "AccessMatrix.java", HW + "Role.java", HW + "Action.java", CH + "access-policy.json"],
       ll=[LL + "rbac.py", CL + "access-policy.json"]),
    ob("ACC-2", "Auditors are read-only", "The auditor role holds no state-changing action.",
       "both", "universal", [(N, "500.7(a)(1)-(2)", "maps to"), (P, "AS 2110 B4; AS 2201 B29", "maps to")],
       domain={"name": "actions", "source": {"baseline-mortgage": [HW + "AccessMatrix.java"], "payments": [LL + "rbac.py"]}, "closed": True},
       hw=[HW + "AccessMatrix.java", HW + "Action.java", CH + "access-policy.json"], ll=[LL + "rbac.py", CL + "access-policy.json"]),
    ob("SOD-1", "IT administrators can't approve credit or release payments",
       "The IT administrator role can never approve, decline or override credit, or approve or release payments.",
       "both", "universal", [(C, "Control Activities; Principle 10", "maps to"), (T, "CC5.1, CC6.3", "maps to")],
       domain={"name": "actions", "source": {"baseline-mortgage": [HW + "AccessMatrix.java"], "payments": [LL + "rbac.py"]}, "closed": True},
       hw=[HW + "AccessMatrix.java", CH + "access-policy.json"], ll=[LL + "rbac.py", CL + "access-policy.json"]),
    ob("MFA-1", "Privileged routes require MFA",
       "Every HTTP route whose action is privileged requires a session that completed multi-factor authentication, and no route is served outside the route table.",
       "both", "universal", [(N, "500.12(a)", "maps to"), (N, "500.12(b) (CISO-approved compensating controls)", "maps to")],
       domain={"name": "routes", "source": {"baseline-mortgage": [HW + "Routes.java"], "payments": [LL + "routes.py"]}, "closed": True},
       hw=[HW + "Routes.java", HW + "Route.java", HW + "HttpApp.java", HW + "Action.java", HW + "Main.java"],
       ll=[LL + "routes.py", LL + "app.py", LL + "rbac.py#PRIVILEGED"]),
    ob("SES-1", "Privileged sessions time out within 15 minutes",
       "A privileged session idle for more than 15 minutes is no longer accepted.",
       "both", "parametric", [(N, "500.7(a)(3) (nearest hook)", "stretch")], severity="high",
       params={"privileged_idle_minutes_max": 15,
               "bounds": [{"key": "mortgage.privileged_idle_minutes", "op": "<=", "value": 15},
                          {"key": "payments.privileged_idle_minutes", "op": "<=", "value": 15}]},
       hw=[HW + "Session.java", HW + "SessionStore.java", HW + "Policy.java#Policy.PRIVILEGED_IDLE_MINUTES", CH + "policy-params.json#mortgage.privileged_idle_minutes"],
       ll=[LL + "session.py", LL + "policy.py#PRIVILEGED_IDLE_MINUTES", CL + "policy-params.json#payments.privileged_idle_minutes"]),
    ob("ENC-1", "NPI is encrypted at rest",
       "Every field holding nonpublic personal information (government identifiers such as SSN or tax id, financial account and routing numbers, date of birth, income) is persisted only in sealed form.",
       "both", "universal", [(N, "500.15(a)", "direct"), (N, "500.15(b)", "maps to")],
       domain={"name": "NPI fields", "source": {"baseline-mortgage": [HW + "NpiRegistry.java"], "payments": [LL + "npi.py"]}, "closed": True},
       hw=[HW + "NpiRegistry.java", HW + "NpiVault.java", HW + "CaseStore.java", HW + "ApplicantFields.java"],
       ll=[LL + "npi.py", LL + "vault.py", LL + "store.py", LL + "models.py"]),
    ob("ENC-2", "Outbound integrations use TLS", "Every outbound integration endpoint uses https.",
       "payments", "universal", [(N, "500.15(a)", "maps to"), (T, "CC6.7", "maps to")],
       domain={"name": "integrations", "source": {"payments": [LL + "integrations.py"]}, "closed": True},
       ll=[LL + "integrations.py", LL + "transports.py"]),
    ob("LOG-1", "NPI never reaches application logs",
       "No application log entry contains an unmasked NPI value, on any path including error paths.",
       "both", "universal", [(N, "500.15(a) (nearest hook)", "stretch"), (T, "C1.1", "maps to")],
       domain={"name": "log call sites", "source": {"baseline-mortgage": [HW + "AppLog.java"], "payments": [LL + "logs.py"]}, "closed": False},
       hw=[HW + "AppLog.java", HW + "Mask.java"], hw_pat=[r"\blog\.(info|warn|warning|error|debug)\(", r"AppLog"],
       ll=[LL + "logs.py", LL + "npi.py#mask"], ll_pat=[r"_log\.(info|warning|error|debug)\(", r"\bAppLog\b"]),
    ob("AUD-1", "State changes are audited",
       "Every state-changing operation records an audit event with actor, action, target and time.",
       "both", "universal", [(N, "500.6(a)(1)-(2)", "maps to")],
       domain={"name": "state-changing operations", "source": {"baseline-mortgage": [HW + "CaseService.java"], "payments": [LL + "service.py"]}, "closed": False},
       hw=[HW + "CaseService.java", HW + "AuditLog.java"], ll=[LL + "service.py", LL + "audit.py"]),
    ob("AUD-2", "Audit trail is tamper-evident and retained",
       "The audit trail is append-only and hash-chained, and events are retained for at least 7 years (the bank's standard; the rule's floors are 5 and 3 years).",
       "both", "parametric", [(N, "500.6(b)", "maps to")],
       params={"audit_retention_years_min": 7,
               "bounds": [{"key": "mortgage.audit_retention_years", "op": ">=", "value": 7},
                          {"key": "payments.audit_retention_years", "op": ">=", "value": 7}]},
       hw=[HW + "AuditLog.java", HW + "AuditEvent.java", HW + "Policy.java#Policy.AUDIT_RETENTION_YEARS", CH + "policy-params.json#mortgage.audit_retention_years"],
       ll=[LL + "audit.py", LL + "policy.py#AUDIT_RETENTION_YEARS", CL + "policy-params.json#payments.audit_retention_years"]),
    ob("RET-1", "NPI is disposed of on schedule unless on legal hold",
       "NPI of declined or withdrawn applications and closed payee accounts is purged after the approved retention period, and never while a legal hold applies.",
       "both", "universal", [(N, "500.13(b)", "maps to"), (T, "C1.2", "maps to")], severity="high",
       hw=[HW + "Retention.java", HW + "Policy.java#Policy.DECLINED_NPI_RETENTION_MONTHS", CH + "policy-params.json#mortgage.declined_npi_retention_months"],
       ll=[LL + "retention.py", LL + "policy.py#CLOSED_ACCOUNT_NPI_RETENTION_MONTHS", LL + "store.py#Store.purge_payee_npi",
           LL + "store.py#Store.closed_payees_before", CL + "policy-params.json#payments.closed_account_npi_retention_months"]),
    ob("INV-1", "Outbound integrations are inventoried",
       "Every outbound integration is listed in the approved asset inventory with an owner and a data classification.",
       "payments", "universal", [(N, "500.13(a)", "direct"), (FA, "III.B.1", "maps to")], severity="high",
       domain={"name": "integrations", "source": {"payments": [LL + "integrations.py"]}, "closed": True},
       ll=[LL + "integrations.py", CL + "asset-inventory.json"]),
    ob("SEC-1", "Database statements are parameterized",
       "Every SQL statement is a fixed string with values bound as parameters; no statement text is built from data.",
       "payments", "universal", [(N, "500.8(a)", "maps to"), (FD, "V.D.2", "maps to")],
       domain={"name": "SQL call sites", "source": {"payments": [LL + "store.py"]}, "closed": False},
       ll=[LL + "store.py"], ll_pat=[r"\.execute(many)?\("]),
    ob("MC-1", "Maker-checker", "Whoever prepared a credit decision or created a payment can't approve it.",
       "both", "universal", [(C, "Control Activities; Principle 10", "maps to"), (T, "CC5.1, CC6.3", "maps to")],
       hw=[HW + "Approvals.java"], ll=[LL + "payments.py#approve", LL + "payments.py#is_fully_approved"]),
    ob("LIM-1", "Approval authority limits",
       "Approval authority follows the approved limits (currently: up to 500,000 one underwriter or senior underwriter; up to 1,500,000 a senior underwriter; above that two distinct senior underwriters), and the limits in code equal the approved values.",
       "baseline-mortgage", "parametric", [(C, "Control Activities", "maps to"), (P, "AS 2201 B30", "maps to")],
       params={"underwriter_limit": 500000, "senior_limit": 1500000},
       hw=[HW + "Approvals.java", HW + "Policy.java#Policy.UNDERWRITER_LIMIT", HW + "Policy.java#Policy.SENIOR_LIMIT", CH + "policy-params.json#mortgage.underwriter_limit", CH + "policy-params.json#mortgage.senior_limit"]),
    ob("CRD-1", "Automated credit decision follows approved policy",
       "Auto-approval is possible only within the approved DTI and LTV limits (currently 40% and 90%), and the parameters in code equal the approved values.",
       "baseline-mortgage", "parametric", [(P, "AS 2201 B29-B30", "maps to")],
       params={"dti_max_percent": 40, "ltv_max_percent": 90},
       hw=[HW + "Underwriting.java", HW + "Policy.java#Policy.DTI_MAX_PERCENT", HW + "Policy.java#Policy.LTV_MAX_PERCENT", CH + "policy-params.json#mortgage.dti_max_percent", CH + "policy-params.json#mortgage.ltv_max_percent"]),
    ob("PAY-1", "Dual control on large payments",
       "A payment at or above the approved dual-control threshold (currently 10,000.00) needs two distinct approvers, neither of them its creator, and the threshold in code equals the approved value.",
       "payments", "universal", [(C, "Control Activities", "maps to"), (T, "CC5.1", "maps to")],
       params={"dual_control_threshold": "10000.00"},
       ll=[LL + "payments.py#required_approvals", LL + "payments.py#is_fully_approved", LL + "policy.py#DUAL_CONTROL_THRESHOLD", CL + "policy-params.json#payments.dual_control_threshold", CL + "policy-params.json#payments.dual_control_approvers"]),
    ob("PAY-2", "A payment instruction is released at most once",
       "Releasing the same payment instruction again never sends a second disbursement.",
       "payments", "universal", [(P, "AS 2201 .28 (assertions)", "maps to")],
       ll=[LL + "payments.py#release", LL + "store.py#Store.find_release", LL + "store.py#Store.add_release"]),
]
PROC = [
    ("CHG-1", "Change ticket", [(FD, "VII.B.1; VII.B.4(a)", "maps to"), (FA, "III.D.1", "maps to"), (T, "CC8.1", "direct")]),
    ("CHG-2", "Independent approval", [(FD, "VII.B.1; VII.B.2(b)-(c)", "maps to"), (T, "CC8.1", "direct")]),
    ("CHG-3", "Approval covers what is merged", [(FD, "VII.B.1; VII.B.2(c)", "maps to"), (T, "CC8.1", "maps to")]),
    ("CHG-4", "Testing on the final commit", [(FD, "V.B; VII.B.1", "maps to"), (T, "CC8.1", "direct"), (P, "AS 2201 .46-.47", "maps to")]),
    ("CHG-5", "Security review of sensitive components", [(N, "500.8(a)", "maps to"), (FD, "IV.D", "maps to")]),
    ("CHG-6", "Control changes need a control owner", [(FD, "IV.K; VII.B.2(c)", "maps to")]),
    ("CHG-7", "Emergency changes get a timely post-implementation review", [(FA, "III.D.1", "maps to"), (FD, "VII.B.3(c)", "maps to")]),
    ("EXC-1", "Exceptions", [(N, "500.12(b); 500.15(b)", "maps to"), (T, "CC5.1, CC4.2", "maps to")]),
    ("LAP-1", "Evidence lapses on change", [(P, "AS 2201 .60; B29; B33", "maps to"), (FD, "VII.B.1", "maps to")]),
]
for oid, title, maps in PROC:
    O.append(ob(oid, title, f"See controls/change-policy.md section {oid}.", "process", "process", maps, owner="Change management"))

doc = {"version": "2026-10-23", "contract": "obligation record v0",
       "note": "Synthetic bank. Obligations paraphrase and 'map to' public rules; none claims to satisfy a regulation.",
       "obligations": O}
out = Path(__file__).resolve().parents[1] / "platform" / "controls" / "obligations.json"
out.write_text(json.dumps(doc, indent=2) + "\n")
print(out, len(O))
