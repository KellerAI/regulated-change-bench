"""Runtime and policy-data changes, paired with narrow independent checks."""
from __future__ import annotations

import json
from ..common import HW, HWT, LL, Family
from .helpers import records, finish, pycheck, javacheck


def coapplicant_identifier(b, mode):
    b.edit(HW + "ApplicantFields.java", '            "employer",', '            "employer",\n            "coapplicant_tax_id",')
    b.edit(HWT + "controls/ControlFixtures.java", '        applicant.put("annual_income", income);',
           '        applicant.put("annual_income", income);\n        applicant.put("coapplicant_tax_id", "93-7291046");')
    # The onboarding migration explicitly handles disposal in either mode, so
    # registry omission isolates encryption rather than also breaking retention.
    b.edit(HW + "Retention.java", "        loanCase.markNpiPurged(clock.instant());",
           '        loanCase.removeApplicantField("coapplicant_tax_id");\n        loanCase.markNpiPurged(clock.instant());')
    # Both changes introduce the field; only one adds it to the storage classification.
    if mode == "clean":
        b.edit(HW + "NpiRegistry.java", '"annual_income");', '"annual_income", "coapplicant_tax_id");')
    b.commit("Applications: retain the co-applicant tax identifier")
    records(b, "Co-applicant onboarding field", ["Accept coapplicant_tax_id on create and edit", "Reuse the existing applicant persistence pipeline", "Include the onboarding field in scheduled disposal and sample applicants"])
    finish(b, mode, ["ENC-1"], "new government identifier persists in plaintext outside the NPI registry")
    javacheck(b, mode, '''
        Fixtures f = new Fixtures();
        Map<String, String> fields = Fixtures.applicant("900-11-0213");
        String identifier = "93-7291046";
        fields.put("coapplicant_tax_id", identifier);
        LoanCase c = f.service.create(Fixtures.PROCESSOR, fields, Fixtures.eligibleLoan());
        Map<?, ?> atRest = (Map<?, ?>) f.store.atRest(c.id()).get("applicant");
        boolean sealed = NpiVault.isSealed((String) atRest.get("coapplicant_tax_id"));
        assertEquals(identifier, f.store.find(c.id()).orElseThrow().applicantField("coapplicant_tax_id"));
        f.service.withdraw(Fixtures.PROCESSOR, c.id());
        f.clock.advanceMonths(30);
        f.service.purgeExpiredNpi(Fixtures.ADMIN);
        assertNull(f.store.find(c.id()).orElseThrow().applicantField("coapplicant_tax_id"));
        assertTrue(sealed);
    ''')


def document_audit(b, mode):
    line = '        audit.record(actor, Action.EDIT_CASE, caseId, "document_received:" + document);'
    replacement = '        log.info("Document " + document + " received for case " + caseId);'
    b.edit(HW + "CaseService.java", line, replacement + ("\n" + line if mode == "clean" else ""))
    b.commit("Documents: consolidate receipt diagnostics")
    records(b, "Document receipt diagnostics", ["Record document receipt in operational diagnostics", "Keep the checklist workflow and response stable"])
    finish(b, mode, ["AUD-1"], "document receipt changes persisted state without an audit event")
    javacheck(b, mode, '''
        Fixtures f = new Fixtures();
        LoanCase c = f.draft(Fixtures.PROCESSOR, "900-11-0315", Fixtures.eligibleLoan());
        int before = f.audit.events().size();
        f.service.markDocumentReceived(Fixtures.PROCESSOR, c.id(), DocumentType.PHOTO_ID);
        assertTrue(f.store.find(c.id()).orElseThrow().receivedDocuments().contains(DocumentType.PHOTO_ID));
        List<AuditEvent> added = f.audit.events().subList(before, f.audit.events().size());
        assertTrue(added.stream().anyMatch(e -> e.actor().equals(Fixtures.PROCESSOR.userId())
            && e.action() == Action.EDIT_CASE && e.target().equals(c.id()) && e.timestamp().equals(f.clock.instant())));
    ''')


def income_validation_log(b, mode):
    old = 'log.warn("Rejected annual income " + Mask.npi(value) + " on " + caseRef);'
    value = "value" if mode == "defect" else "Mask.npi(value)"
    b.edit(HW + "ApplicantValidator.java", old, 'log.warn("Annual income format rejected on " + caseRef + ": " + ' + value + ');')
    b.commit("Validation: improve income formatting diagnostics")
    records(b, "Income formatting diagnostics", ["Help operations identify rejected import values", "Keep validation and API error messages unchanged"])
    finish(b, mode, ["LOG-1"], "income validation error writes the raw supplied NPI to application logs")
    javacheck(b, mode, '''
        Fixtures f = new Fixtures();
        String income = "127,893.42";
        assertThrows(ServiceException.class, () -> new ApplicantValidator(f.log).validate("HW-041901", Map.of("annual_income", income)));
        assertFalse(String.join("\\n", f.log.lines()).contains(income));
    ''')


def withdrawn_hold(b, mode):
    b.edit(HW + "Retention.java", "if (loanCase.isLegalHold()) {", "if (loanCase.isLegalHold()" + (" && loanCase.status() != CaseStatus.WITHDRAWN" if mode == "defect" else " && isClosedOut(loanCase.status())") + ") {")
    b.commit("Retention: align withdrawn case handling with closure processing")
    records(b, "Withdrawn case retention alignment", ["Simplify hold handling after a case leaves the active pipeline", "Keep the established retention interval"])
    finish(b, mode, ["RET-1"], "expired withdrawn cases lose NPI despite an active legal hold", severity="high")
    javacheck(b, mode, '''
        Fixtures f = new Fixtures();
        LoanCase c = f.draft(Fixtures.PROCESSOR, "900-13-6290", Fixtures.eligibleLoan());
        f.service.withdraw(Fixtures.PROCESSOR, c.id());
        f.service.setLegalHold(Fixtures.ADMIN, c.id(), true);
        f.clock.advanceMonths(30);
        assertTrue(f.service.purgeExpiredNpi(Fixtures.ADMIN).isEmpty());
        assertEquals("900-13-6290", f.store.find(c.id()).orElseThrow().applicantField("ssn"));
    ''')


def compatibility_route(b, mode):
    if mode == "defect":
        b.edit(LL + "app.py", '    path_known = False\n', '''    compatibility_id = re.fullmatch(r"/compat/account-number/([0-9]+)", path)
    if method == "GET" and compatibility_id:
        return Route("GET", "/payees/{id}/account-number", "view_account_number", mfa=False), int(compatibility_id.group(1))
    path_known = False
''')
    else:
        b.edit(LL + "routes.py", "ROUTES = [", '''ROUTES = [
    Route("GET", "/compat/account-number/{id}", "view_account_number", mfa=True),''')
        b.edit(LL + "app.py", 'HANDLERS = {', 'HANDLERS = {\n    "GET /compat/account-number/{id}": _reveal_account_number,')
    b.commit("API: support the account-number compatibility URL")
    records(b, "Account-number URL compatibility", ["Keep the earlier mobile client URL working", "Reuse account-number service authorization"])
    finish(b, mode, ["MFA-1"], "compatibility route is served outside the route table and bypasses MFA")
    pycheck(b, mode, '''
        from support import actor, details
        def test_acceptance_runtime(service, client, login):
            payee = service.add_payee(actor("officer.ben"), details())
            assert payee.id == 1
            response = client.get("/compat/account-number/1", login("treasury.dee", mfa=False))
            assert response.status == 403
            assert response.json()["error"] == "mfa_required"
    ''')


def archive_transport(b, mode):
    b.edit(LL + "integrations.py", '        return integration.base_url.rstrip("/") + "/" + path.lstrip("/")', '''        base = integration.base_url
        if name == "statement-delivery" and path.startswith("/archive/"):
            base = base.replace("https://", "SCHEME://", 1)
        return base.rstrip("/") + "/" + path.lstrip("/")'''.replace("SCHEME", "http" if mode == "defect" else "https"))
    b.commit("Statements: support archive delivery paths")
    records(b, "Statement archive path support", ["Allow archive delivery through the existing statement gateway", "Retain the gateway host and integration name"])
    finish(b, mode, ["ENC-2"], "archive delivery downgrades a registered outbound endpoint to HTTP")
    pycheck(b, mode, '''
        from urllib.parse import urlsplit
        from payments.integrations import OutboundClient
        from payments.transports import RecordingTransport
        def test_acceptance_runtime():
            transport = RecordingTransport()
            OutboundClient(transport).post("statement-delivery", "/archive/2026-09", {"document": "statement"})
            assert transport.requests
            assert all(urlsplit(url).scheme == "https" for url, _ in transport.requests)
    ''')


def statement_failure_log(b, mode):
    old = '            self._log.error("statement delivery failed", payee_id=payee_id)'
    value = 'self._store.get_payee(payee_id).account_number'
    if mode == "defect":
        new = '            self._log.error(f"statement delivery failed for account {' + value + '}", payee_id=payee_id)'
    else:
        new = '            self._log.error("statement delivery failed", payee_id=payee_id, account_number=' + value + ')'
    b.edit(LL + "service.py", old, new)
    b.commit("Statements: add account context to delivery errors")
    records(b, "Statement delivery error context", ["Give support staff account context when a statement gateway request fails", "Use the existing application logger"])
    finish(b, mode, ["LOG-1"], "statement delivery failure interpolates account NPI into the log message")
    pycheck(b, mode, '''
        import pytest
        from payments.errors import IntegrationError
        from payments.logs import MemorySink
        from support import STATEMENTS, actor, details
        def test_acceptance_runtime(service, transport):
            payee = service.add_payee(actor("officer.ben"), details())
            transport.fail(STATEMENTS)
            sink = MemorySink().attach()
            try:
                with pytest.raises(IntegrationError):
                    service.deliver_statement(actor("clerk.ana"), payee.id, 2026, 9)
            finally:
                sink.detach()
            assert "statement delivery failed" in sink.text()
            assert "880012345678" not in sink.text()
    ''')


def memo_audit(b, mode):
    old = '        self._audit(actor, "amend_memo", f"payment:{payment_id}")'
    new = '        self._log.info("payment memo updated", payment_id=payment_id)'
    b.edit(LL + "service.py", old, new + ("\n" + old if mode == "clean" else ""))
    b.commit("Payments: streamline memo update telemetry")
    records(b, "Memo update telemetry", ["Use consistent payment-id diagnostics for memo edits", "Preserve creator checks and persistence"])
    finish(b, mode, ["AUD-1"], "persisted memo changes produce diagnostics but no audit event")
    pycheck(b, mode, '''
        from support import actor, details
        def test_acceptance_runtime(service, clock):
            payee = service.add_payee(actor("officer.ben"), details())
            maker = actor("clerk.ana")
            payment = service.create_payment(maker, payee.id, "12.00")
            before = len(service.audit_log.events())
            service.amend_memo(maker, payment.id, "Invoice 902")
            assert service.store.get_payment(payment.id).memo == "Invoice 902"
            added = service.audit_log.events()[before:]
            assert [(e.actor, e.action, e.target, e.at) for e in added] == [
                (maker.user_id, "amend_memo", f"payment:{payment.id}", clock.now())]
    ''')


def release_cache(b, mode):
    b.edit(LL + "payments.py", "from datetime import datetime", "from datetime import datetime, timedelta")
    condition = "previous is not None"
    if mode == "defect":
        condition += " and now - previous.released_at < timedelta(days=1)"
    b.edit(LL + "payments.py", '    if previous is not None:\n        return previous', '    # Reuse the persisted confirmation for a replayed instruction.\n    if ' + condition + ':\n        return previous')
    b.commit("Payments: reuse recent disbursement confirmations")
    records(b, "Disbursement confirmation reuse", ["Reduce repeat gateway requests using persisted confirmations", "Use the existing instruction identifier"])
    finish(b, mode, ["PAY-2"], "idempotency lookup expires after one day and a later retry sends again")
    pycheck(b, mode, '''
        from support import actor, details, CORE_BANKING
        def test_acceptance_runtime(service, transport, clock):
            payee = service.add_payee(actor("officer.ben"), details())
            payment = service.create_payment(actor("clerk.ana"), payee.id, "12.00")
            service.approve_payment(actor("officer.ben"), payment.id)
            first = service.release_payment(actor("treasury.dee"), payment.id)
            clock.advance(days=2)
            second = service.release_payment(actor("treasury.dee"), payment.id)
            assert len(transport.sent_to(CORE_BANKING)) == 1
            assert second == first
    ''')


def report_action_alias(b, mode):
    check = '(role, action.removeprefix("report:"))' if mode == "defect" else '(role, action)'
    b.edit(LL + "rbac.py", '    return (role, action) in GRANTS', '    if action.startswith("report:"):\n        return ' + check + ' in GRANTS\n    return (role, action) in GRANTS')
    b.commit("Access: support reporting client action names")
    records(b, "Reporting action compatibility", ["Prepare the reporting client namespace", "Delegate decisions to the existing explicit grants matrix"])
    finish(b, mode, ["ACC-1"], "unapproved namespaced actions are granted by stripping a prefix")
    pycheck(b, mode, '''
        from payments import rbac
        def test_acceptance_runtime():
            for action in ("report:view_reports", "report:view_account", "report:export_ledger"):
                assert not rbac.is_allowed("treasury_manager", action), action
            assert rbac.is_allowed("treasury_manager", "view_reports")
    ''')


def inventory_owner(b, mode):
    b.edit(LL + "integrations.py", "INTEGRATIONS = [", 'INTEGRATIONS = [\n    Integration("payment-advice", "https://advice.fernbrook.example/v1"),')
    path = "controls/payments/asset-inventory.json"
    doc = json.loads(b.read(path))
    doc["integrations"].append({"name": "payment-advice", "host": "advice.fernbrook.example", "owner": "" if mode == "defect" else "payments-operations", "data_classification": doc["classifications"][0]})
    b.write(path, json.dumps(doc, indent=2) + "\n")
    b.commit("Integrations: register the payment advice gateway")
    records(b, "Payment advice gateway registration", ["Add the HTTPS gateway to the integration registry and inventory", "Ownership handoff is tracked in the inventory entry"],)
    finish(b, mode, ["INV-1", "CHG-4"], "new integration has no accountable owner and its registered control fails")
    pycheck(b, mode, '''
        import json
        from support import platform_root
        from payments.integrations import INTEGRATIONS
        def test_acceptance_runtime():
            entries = json.loads((platform_root() / "controls/payments/asset-inventory.json").read_text())["integrations"]
            inventory = {e["name"]: e for e in entries}
            assert all(inventory[i.name].get("owner") for i in INTEGRATIONS)
    ''')
    b.oracle("ci", tests=["test_integrations_are_inventoried"], expect="fail" if mode == "defect" else "pass")


FAMILIES = [
    Family("coapplicant_identifier", "baseline-mortgage", coapplicant_identifier),
    Family("document_receipt_journal", "baseline-mortgage", document_audit),
    Family("income_format_diagnostics", "baseline-mortgage", income_validation_log),
    Family("withdrawal_hold_lifecycle", "baseline-mortgage", withdrawn_hold),
    Family("account_url_compatibility", "payments", compatibility_route),
    Family("statement_archive_transport", "payments", archive_transport),
    Family("statement_error_context", "payments", statement_failure_log),
    Family("memo_update_telemetry", "payments", memo_audit),
    Family("confirmation_reuse_window", "payments", release_cache),
    Family("report_action_namespace", "payments", report_action_alias),
    Family("advice_gateway_inventory", "payments", inventory_owner),
]
