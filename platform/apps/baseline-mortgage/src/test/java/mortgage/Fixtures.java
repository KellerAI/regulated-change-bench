package mortgage;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/** A wired service with synthetic people and applicants for unit tests. */
final class Fixtures {

    static final Instant START = Instant.parse("2026-05-11T14:30:00Z");

    static final Actor APPLICANT = new Actor("app-lena", Role.APPLICANT);
    static final Actor OTHER_APPLICANT = new Actor("app-tomas", Role.APPLICANT);
    static final Actor PROCESSOR = new Actor("proc-ada", Role.PROCESSOR);
    static final Actor UNDERWRITER = new Actor("uw-ben", Role.UNDERWRITER);
    static final Actor SECOND_UNDERWRITER = new Actor("uw-cora", Role.UNDERWRITER);
    static final Actor SENIOR = new Actor("suw-dev", Role.SENIOR_UNDERWRITER);
    static final Actor SECOND_SENIOR = new Actor("suw-eli", Role.SENIOR_UNDERWRITER);
    static final Actor AUDITOR = new Actor("aud-fay", Role.AUDITOR);
    static final Actor ADMIN = new Actor("adm-gus", Role.ADMIN);

    final TestClock clock = new TestClock(START);
    final AppLog log = new AppLog(clock);
    final AuditLog audit = new AuditLog(clock);
    final CaseStore store = CaseStore.inMemory(new NpiVault());
    final CaseService service = new CaseService(store, audit, log, clock);

    static Map<String, String> applicant(String ssn) {
        Map<String, String> applicant = new LinkedHashMap<>();
        applicant.put("full_name", "Lena Marsh");
        applicant.put("email", "lena.marsh@example.test");
        applicant.put("phone", "555-0142");
        applicant.put("employer", "Northgate Bakery");
        applicant.put("self_employed", "false");
        applicant.put("ssn", ssn);
        applicant.put("date_of_birth", "1988-02-29");
        applicant.put("bank_account_number", "000123456789");
        applicant.put("annual_income", "120000");
        return applicant;
    }

    /** 200,000 against a 400,000 appraisal with 500 of other debt: well inside policy. */
    static LoanRequest eligibleLoan() {
        return loan("200000", "400000", "500");
    }

    /** Same loan with 3,500 of other debt: DTI around 47%, so referred. */
    static LoanRequest referredLoan() {
        return loan("200000", "400000", "3500");
    }

    static LoanRequest loan(String amount, String appraisedValue, String monthlyDebt) {
        return new LoanRequest(new BigDecimal(amount), new BigDecimal(appraisedValue), new BigDecimal(monthlyDebt));
    }

    LoanCase draft(Actor creator, String ssn, LoanRequest loan) {
        return service.create(creator, applicant(ssn), loan);
    }

    /** A draft with all documents and a 30-year quote, ready to submit. */
    LoanCase ready(Actor creator, String ssn, LoanRequest loan) {
        return ready(creator, applicant(ssn), loan);
    }

    LoanCase ready(Actor creator, Map<String, String> applicant, LoanRequest loan) {
        LoanCase draft = service.create(creator, applicant, loan);
        for (DocumentType document : DocumentChecklist.required(draft)) {
            service.markDocumentReceived(creator, draft.id(), document);
        }
        service.quote(creator, draft.id(), 30);
        return service.view(creator, draft.id());
    }

    LoanCase submitted(String ssn, LoanRequest loan) {
        return submitted(applicant(ssn), loan);
    }

    LoanCase submitted(Map<String, String> applicant, LoanRequest loan) {
        LoanCase ready = ready(PROCESSOR, applicant, loan);
        return service.submit(PROCESSOR, ready.id());
    }
}
