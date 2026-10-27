"""Dev pack: baseline-mortgage (Java loan origination) families."""
from __future__ import annotations

import json
from datetime import timedelta

from ...builder import iso
from ..common import HW, HWT, Family, describe

APP = "baseline-mortgage"
T = HWT + "mortgage/"


# ---------------------------------------------------------------------------------------- carriers
def carrier_pipeline_total(b) -> str:
    b.edit(HW + "PipelineReport.java", '''    public Row row(CaseStatus status) {''', '''    /** Number of cases across every status. */
    public int totalCases() {
        int total = 0;
        for (Row row : rows) {
            total += row.count();
        }
        return total;
    }

    public Row row(CaseStatus status) {''')
    b.write(T + "PipelineTotalTest.java", '''package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class PipelineTotalTest {

    @Test
    void emptyPipelineHasNoCases() {
        PipelineReport report = PipelineReport.build(List.of(), Instant.parse("2026-09-01T00:00:00Z"));
        assertEquals(0, report.totalCases());
    }
}
''')
    return b.commit("Pipeline report: total case count")


def carrier_quote_terms(b) -> str:
    b.edit(HW + "RateQuote.java", '''    public static RateQuote price(BigDecimal loanAmount, BigDecimal appraisedValue, int termYears, Instant quotedAt) {''',
           '''    /** Whether a term (in years) can be quoted. */
    public static boolean isSupportedTerm(int termYears) {
        return TERMS_YEARS.contains(termYears);
    }

    public static RateQuote price(BigDecimal loanAmount, BigDecimal appraisedValue, int termYears, Instant quotedAt) {''')
    b.write(T + "QuoteTermTest.java", '''package mortgage;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class QuoteTermTest {

    @Test
    void thirtyYearsIsSupported() {
        assertTrue(RateQuote.isSupportedTerm(30));
    }

    @Test
    void tenYearsIsNot() {
        assertFalse(RateQuote.isSupportedTerm(10));
    }
}
''')
    return b.commit("Rate quote: expose supported terms")


CARRIERS = [carrier_pipeline_total, carrier_quote_terms]
CARRIER_TEXT = {
    "carrier_pipeline_total": ("Pipeline report: total case count", ["Add `PipelineReport.totalCases`", "Unit test"]),
    "carrier_quote_terms": ("Rate quote: supported terms helper", ["Add `RateQuote.isSupportedTerm`", "Unit tests"]),
}


def carrier(b):
    fn = b.rng.choice(CARRIERS)
    return fn.__name__, fn(b)


def text_for(name):
    return CARRIER_TEXT[name]


def follow_up(b, semantic: bool) -> str:
    if semantic:
        b.edit(HW + "RateQuote.java", '    static final Set<Integer> TERMS_YEARS = Set.of(15, 20, 30);',
               '    static final Set<Integer> TERMS_YEARS = Set.of(15, 20, 30);\n    static final int DEFAULT_TERM_YEARS = 30;')
        return b.commit(b.rng.choice(["Rate quote: default term constant", "Add default quote term"]))
    b.edit(HW + "RateQuote.java", '    static final Set<Integer> TERMS_YEARS = Set.of(15, 20, 30);',
           '    // Terms offered on the rate sheet.\n    static final Set<Integer> TERMS_YEARS = Set.of(15, 20, 30);')
    return b.commit(b.rng.choice(["Comment the rate sheet terms", "Docs: note where terms come from"]))


def carrier_sensitive(b):
    b.edit(HW + "AppLog.java", '''    public void error(String message) {
        write("ERROR", message);
    }''', '''    public void error(String message) {
        write("ERROR", message);
    }

    /** Most recent line, or an empty string when nothing has been logged. */
    public synchronized String last() {
        return lines.isEmpty() ? "" : lines.peekLast();
    }''')
    b.commit("AppLog: expose the most recent line for the ops console")
    return "Ops console: most recent log line", ["Add `AppLog.last()`"]


def control_param_change(b):
    b.edit(HW + "Policy.java", "    public static final int STANDARD_IDLE_MINUTES = 30;", "    public static final int STANDARD_IDLE_MINUTES = 45;")
    params = json.loads(b.read("controls/mortgage/policy-params.json"))
    params["mortgage.standard_idle_minutes"] = 45
    b.write("controls/mortgage/policy-params.json", json.dumps(params, indent=2) + "\n")
    b.edit(T + "SessionTest.java", "        clock.advance(Duration.ofMinutes(31));", "        clock.advance(Duration.ofMinutes(46));")
    b.commit("Sessions: 45 minute idle timeout for standard sessions")


# ---------------------------------------------------------------------------------------- helpers
HIDDEN = T + "HiddenCheckTest.java"


def hidden(b, body: str, expect: str):
    helper = (
        "    static String source(String name) throws Exception {\n"
        "        java.nio.file.Path dir = java.nio.file.Path.of(System.getProperty(\"user.dir\")).toAbsolutePath();\n"
        "        for (int i = 0; i < 6 && dir != null; i++, dir = dir.getParent()) {\n"
        "            for (String rel : new String[] {\"src/main/java/mortgage/\", \"apps/baseline-mortgage/src/main/java/mortgage/\"}) {\n"
        "                java.nio.file.Path p = dir.resolve(rel + name);\n"
        "                if (java.nio.file.Files.exists(p)) {\n"
        "                    return java.nio.file.Files.readString(p);\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "        throw new IllegalStateException(\"source not found: \" + name);\n"
        "    }\n")
    src = "package mortgage;\n\nimport static org.junit.jupiter.api.Assertions.*;\n\nimport java.math.BigDecimal;\nimport java.util.*;\nimport org.junit.jupiter.api.Test;\n\nclass HiddenCheckTest {\n" + helper + body + "\n}\n"
    b.oracle("hidden_test", files={HIDDEN: src}, tests=["HiddenCheckTest"], expect=expect)


def ok_process(b, except_=()):
    b.oracle("predicate", name="process_ok", args={"except_": list(except_)}, expect=True)


def set_param(b, key, value):
    params = json.loads(b.read("controls/mortgage/policy-params.json"))
    params[key] = value
    b.write("controls/mortgage/policy-params.json", json.dumps(params, indent=2) + "\n")


def renew_proof(b, name: str, statement: str):
    head = b.records["change"]["head"]
    doc = dict(b.records["evidence"][name])
    doc["target"] = {**doc["target"], "commit": head}
    entry = next(e for e in b.records["ledger"] if e["evidence"].get("ref", "").endswith(name))
    doc["covers"] = [c for c in entry["evidence"]["covers"] if c != {k: v for k, v in doc["target"].items() if k != "commit"}]
    doc["statement_id"] = statement
    doc["checked_at"] = iso(b.as_of - timedelta(hours=b.rng.randint(2, 20)))
    b.records["evidence"][name.replace(".json", "-renewed.json")] = doc


# ---------------------------------------------------------------------------------------- families
def dti_policy_change(b, mode):
    b.edit(HW + "Policy.java", 'DTI_MAX_PERCENT = new BigDecimal("40");', 'DTI_MAX_PERCENT = new BigDecimal("43");')
    set_param(b, "mortgage.dti_max_percent", 43)
    b.edit(T + "UnderwritingTest.java", 'application("300000", "400000", "96000", "1500", "1847.15")',
           'application("300000", "400000", "96000", "2000", "1847.15")')
    b.commit(b.rng.choice(["Credit policy: DTI ceiling 43%", "Raise auto-approve DTI ceiling to 43%"]))
    b.default_records("Credit policy update: DTI ceiling 43%",
                      describe(b, "Credit committee raised the auto-approve DTI ceiling (minutes CP-2026-31).",
                               ["`Policy.DTI_MAX_PERCENT` 40 -> 43", "Approved parameter updated"]))
    if mode == "defect":
        b.records["approvals"] = [a for a in b.records["approvals"] if a["kind"] != "control_owner"]
        b.label("defect", ["CHG-6", "CRD-1", "LAP-1"], "critical", "credit parameter and approved value changed without a control owner; proof premise changed")
        b.oracle("predicate", name="violated", args={"obligation": "CHG-6"}, expect=True)
        ok_process(b, ["CHG-6", "LAP-1"])
    else:
        b.label("clean")
        ok_process(b)


def authority_tier(b, mode):
    c1 = carrier(b)[1]
    if mode == "defect":
        b.edit(HW + "Approvals.java", "        if (amount.compareTo(Policy.UNDERWRITER_LIMIT) <= 0) {",
               "        if (amount.compareTo(Policy.SENIOR_LIMIT) <= 0 && amount.compareTo(Policy.UNDERWRITER_LIMIT.add(Policy.UNDERWRITER_LIMIT)) <= 0) {")
        b.commit(b.rng.choice(["Approvals: simplify authority tiers", "Let underwriters approve up to twice their limit"]))
    else:
        b.edit(HW + "Approvals.java", "    public static Requirement requiredApprovals(BigDecimal amount) {",
               "    // Authority tiers follow the approved limits in Policy.\n    public static Requirement requiredApprovals(BigDecimal amount) {")
        b.commit("Comment the authority tiers")
    b.ci_commit = c1
    b.default_records("Approval queue clean-up", describe(b, "Small clean-ups in the approval path.", ["See commits"]))
    hidden(b, '''    @Test
    void hiddenCheck() {
        assertEquals(Role.SENIOR_UNDERWRITER, Approvals.requiredApprovals(new BigDecimal("500001")).minimumRole());
        assertEquals(Role.UNDERWRITER, Approvals.requiredApprovals(new BigDecimal("500000")).minimumRole());
    }''', "fail" if mode == "defect" else "pass")
    if mode == "defect":
        b.label("defect", ["LIM-1", "CHG-4", "LAP-1"], "critical", "underwriter authority widened after CI ran")
        b.oracle("predicate", name="violated", args={"obligation": "CHG-4"}, expect=True)
        ok_process(b, ["CHG-4", "LAP-1"])
    else:
        b.label("clean")
        ok_process(b)


def npi_field(b, mode):
    b.edit(HW + "ApplicantFields.java", '''            "annual_income");

    public static final List<String> REQUIRED_FOR_SUBMIT''', '''            "annual_income",
            "tax_id");

    public static final List<String> REQUIRED_FOR_SUBMIT''')
    if mode == "clean":
        b.edit(HW + "NpiRegistry.java", 'Set.of("ssn", "date_of_birth", "bank_account_number", "annual_income")',
               'Set.of("ssn", "date_of_birth", "bank_account_number", "annual_income", "tax_id")')
        params = json.loads(b.read("controls/mortgage/policy-params.json"))
        params["mortgage.npi_fields"] = sorted(set(params["mortgage.npi_fields"]) | {"tax_id"})
        b.write("controls/mortgage/policy-params.json", json.dumps(params, indent=2) + "\n")
        b.edit(HWT + "controls/ControlFixtures.java", '        applicant.put("annual_income", income);',
               '        applicant.put("annual_income", income);\n        applicant.put("tax_id", "12-3456789");')
    b.commit(b.rng.choice(["Applicant: capture tax id for self-employed borrowers", "Add tax_id applicant field"]))
    b.default_records("Capture tax id for self-employed applicants",
                      describe(b, "Self-employed applicants need a tax id on file for income verification.",
                               ["New applicant field `tax_id`"]))
    hidden(b, '''    @Test
    void hiddenCheck() {
        assertTrue(NpiRegistry.isNpi("tax_id"), "tax_id holds a government identifier");
    }''', "fail" if mode == "defect" else "pass")
    b.label("defect", ["ENC-1"], "critical", "government identifier field stored outside the NPI registry") if mode == "defect" else b.label("clean")
    ok_process(b)


def decline_log(b, mode):
    expr = 'loanCase.applicantField("ssn")' if mode == "defect" else 'Mask.npi(loanCase.applicantField("ssn"))'
    b.edit(HW + "CaseService.java", '''        log.info("Case " + caseId + " declined by " + actor.userId());''',
           f'''        log.info("Case " + caseId + " declined by " + actor.userId() + " for applicant " + {expr});''')
    b.commit(b.rng.choice(["Decline log: identify the applicant", "Ops: include applicant reference in decline log"]))
    b.default_records("Identify the applicant in decline log lines",
                      describe(b, "Collections asked to match declines to applicants from the log stream.", ["Decline log line names the applicant"]))
    hidden(b, '''    @Test
    void hiddenCheck() throws Exception {
        String src = source("CaseService.java");
        assertFalse(src.contains("+ loanCase.applicantField(\\"ssn\\")"), "raw SSN reaches the log");
    }''', "fail" if mode == "defect" else "pass")
    b.label("defect", ["LOG-1"], "critical", "SSN in the decline log line") if mode == "defect" else b.label("clean")
    ok_process(b)


def unaudited_op(b, mode):
    audit = "" if mode == "defect" else '        audit.record(actor, Action.EDIT_CASE, caseId, "reopened");\n'
    b.edit(HW + "CaseService.java", '''    public LoanCase close(Actor actor, String caseId) {''', f'''    public LoanCase reopen(Actor actor, String caseId) {{
        authorize(actor, Action.EDIT_CASE);
        LoanCase loanCase = load(actor, caseId);
        if (loanCase.status() != CaseStatus.WITHDRAWN) {{
            throw new ServiceException(ServiceException.VALIDATION, "Only withdrawn cases can be reopened");
        }}
        loanCase.moveTo(CaseStatus.DRAFT, clock.instant());
        store.save(loanCase);
{audit}        log.info("Case " + caseId + " reopened by " + actor.userId());
        return loanCase;
    }}

    public LoanCase close(Actor actor, String caseId) {{''')
    b.commit(b.rng.choice(["Cases: reopen a withdrawn case", "Allow processors to reopen withdrawn cases"]))
    b.default_records("Reopen withdrawn cases", describe(b, "Applicants who withdraw by mistake currently have to start over.",
                                                          ["`CaseService.reopen`"]))
    hidden(b, '''    @Test
    void hiddenCheck() throws Exception {
        String src = source("CaseService.java");
        int start = src.indexOf("public LoanCase reopen(");
        int end = src.indexOf("public LoanCase close(");
        assertTrue(src.substring(start, end).contains("audit.record"), "reopen changes state without an audit event");
    }''', "fail" if mode == "defect" else "pass")
    b.label("defect", ["AUD-1"], "high", "new state-changing operation without an audit event") if mode == "defect" else b.label("clean")
    ok_process(b)


def legal_hold_withdrawn(b, mode):
    if mode == "defect":
        b.edit(HW + "Retention.java", '''        if (loanCase.isLegalHold()) {
            return false;
        }''', '''        if (loanCase.isLegalHold() && loanCase.status() == CaseStatus.DECLINED) {
            return false;
        }''')
        b.commit("Retention: legal holds apply to declined cases")
    else:
        b.edit(HW + "Retention.java", '''        if (loanCase.isLegalHold()) {
            return false;
        }''', '''        if (isHeld(loanCase)) {
            return false;
        }''')
        b.edit(HW + "Retention.java", '''    private static boolean isClosedOut(CaseStatus status) {''', '''    private static boolean isHeld(LoanCase loanCase) {
        return loanCase.isLegalHold();
    }

    private static boolean isClosedOut(CaseStatus status) {''')
        b.commit("Retention: extract the legal-hold check")
    b.default_records("Retention clean-up", describe(b, "Tidies the retention eligibility checks.", ["Legal-hold check"]))
    hidden(b, '''    @Test
    void hiddenCheck() {
        java.time.Clock clock = java.time.Clock.fixed(java.time.Instant.parse("2030-01-01T00:00:00Z"), java.time.ZoneOffset.UTC);
        LoanCase c = new LoanCase("c-1", "u-1", "u-1", java.time.Instant.parse("2026-01-01T00:00:00Z"));
        c.moveTo(CaseStatus.WITHDRAWN, java.time.Instant.parse("2026-01-02T00:00:00Z"));
        c.setLegalHold(true);
        assertFalse(new Retention(clock).isPurgeDue(c));
    }''', "fail" if mode == "defect" else "pass")
    b.label("defect", ["RET-1"], "high", "legal hold ignored for withdrawn cases") if mode == "defect" else b.label("clean")
    ok_process(b)


def session_param(b, mode):
    new = 20 if mode == "defect" else 10
    b.edit(HW + "Policy.java", "PRIVILEGED_IDLE_MINUTES = 15;", f"PRIVILEGED_IDLE_MINUTES = {new};")
    set_param(b, "mortgage.privileged_idle_minutes", new)
    if new >= 20:
        b.edit(T + "SessionTest.java", """        Session session = new Session("t", "uw-ben", Role.UNDERWRITER, true, clock);
        clock.advance(Duration.ofMinutes(20));""", """        Session session = new Session("t", "uw-ben", Role.UNDERWRITER, true, clock);
        clock.advance(Duration.ofMinutes(25));""")
    b.commit(f"Privileged idle timeout {new} minutes")
    b.default_records(f"Privileged idle timeout {new} minutes",
                      describe(b, "Adjusts the privileged session window.", [f"`Policy.PRIVILEGED_IDLE_MINUTES` to {new}", "Approved parameter updated"]))
    hidden(b, '''    @Test
    void hiddenCheck() {
        assertTrue(Policy.PRIVILEGED_IDLE_MINUTES <= 15);
    }''', "fail" if mode == "defect" else "pass")
    b.label("defect", ["SES-1"], "high", "privileged idle timeout above 15 minutes") if mode == "defect" else b.label("clean")
    ok_process(b)


def export_route(b, mode):
    flag = "false" if mode == "defect" else "true"
    b.edit(HW + "Routes.java", '''            new Route("GET", "/exports/cases", Action.EXPORT_CASES, true),''',
           f'''            new Route("GET", "/exports/cases", Action.EXPORT_CASES, true),
            new Route("GET", "/exports/cases.csv", Action.EXPORT_CASES, {flag}),''')
    text = b.read(HW + "HttpApp.java")
    anchor = next(line for line in text.splitlines() if 'handlers.put("GET /exports/cases"' in line)
    b.edit(HW + "HttpApp.java", anchor, anchor + "\n" + anchor.replace('"GET /exports/cases"', '"GET /exports/cases.csv"'))
    b.commit("Exports: CSV alias for the case export")
    b.default_records("CSV alias for case export", describe(b, "The BI tool can only fetch URLs ending in .csv.", ["New route alias"]))
    if mode == "defect":
        b.label("defect", ["MFA-1", "CHG-4"], "critical", "privileged export route without MFA; CI red")
        b.oracle("ci", tests=["privilegedRoutesRequireMfa"], expect="fail")
        ok_process(b, ["CHG-4"])
    else:
        b.label("clean")
        b.oracle("ci", tests=["privilegedRoutesRequireMfa"], expect="pass")
        ok_process(b)


FAMILIES = [
    Family("hw_dti_policy_change", APP, dti_policy_change, after_prior=lambda b, m: renew_proof(b, "proofs/crd1-auto-approve.json", "mortgage.auto_approve.v2") if m == "clean" else None),
    Family("hw_authority_tier", APP, authority_tier),
    Family("hw_npi_field", APP, npi_field),
    Family("hw_decline_log", APP, decline_log),
    Family("hw_unaudited_op", APP, unaudited_op),
    Family("hw_legal_hold_withdrawn", APP, legal_hold_withdrawn),
    Family("hw_session_param", APP, session_param),
    Family("hw_export_route", APP, export_route),
]
