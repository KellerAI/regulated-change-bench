package controls;

import mortgage.AccessMatrix;
import mortgage.Action;
import mortgage.Actor;
import mortgage.AppLog;
import mortgage.AuditLog;
import mortgage.CaseService;
import mortgage.CaseStore;
import mortgage.DocumentChecklist;
import mortgage.DocumentType;
import mortgage.LoanCase;
import mortgage.LoanRequest;
import mortgage.NpiVault;
import mortgage.Role;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/** A wired service over an in-memory store, with synthetic applicants. */
final class ControlFixtures {

    static final Instant START = Instant.parse("2026-03-02T09:00:00Z");
    static final int QUOTE_TERM_YEARS = 30;

    final ControlClock clock = new ControlClock(START);
    final AppLog log = new AppLog(clock);
    final AuditLog audit = new AuditLog(clock);
    final CaseStore store = CaseStore.inMemory(new NpiVault());
    final CaseService service = new CaseService(store, audit, log, clock);

    static Actor actor(String userId, Role role) {
        return new Actor(userId, role);
    }

    static Map<String, String> applicant(String name, String ssn, String dateOfBirth, String account, String income) {
        Map<String, String> applicant = new LinkedHashMap<>();
        applicant.put("full_name", name);
        applicant.put("email", name.toLowerCase(Locale.ROOT).replace(' ', '.') + "@example.test");
        applicant.put("employer", "Synthetic Works Ltd");
        applicant.put("self_employed", "false");
        applicant.put("ssn", ssn);
        applicant.put("date_of_birth", dateOfBirth);
        applicant.put("bank_account_number", account);
        applicant.put("annual_income", income);
        return applicant;
    }

    static LoanRequest loan(String amount, String appraisedValue, String monthlyDebt) {
        return new LoanRequest(new BigDecimal(amount), new BigDecimal(appraisedValue), new BigDecimal(monthlyDebt));
    }

    /** Creates a draft with every required document received and a rate quote, ready to submit. */
    LoanCase readyCase(Actor creator, Map<String, String> applicant, LoanRequest loan) {
        LoanCase created = service.create(creator, applicant, loan);
        prepare(creator, created.id());
        return service.view(creator, created.id());
    }

    void prepare(Actor creator, String caseId) {
        LoanCase draft = service.view(creator, caseId);
        for (DocumentType document : DocumentChecklist.required(draft)) {
            service.markDocumentReceived(creator, caseId, document);
        }
        service.quote(creator, caseId, QUOTE_TERM_YEARS);
    }

    /** Privileged by the approved policy or by the code's own classification. */
    static boolean isPrivileged(Action action, Set<String> approvedPrivileged) {
        return action.isPrivileged() || approvedPrivileged.contains(action.name());
    }

    /** A role that holds the action, so a request reaches the checks that follow authentication. */
    static Role roleHolding(Action action) {
        for (Role role : Role.values()) {
            if (AccessMatrix.isAllowed(role, action)) {
                return role;
            }
        }
        return Role.ADMIN;
    }

    static String concretePath(String pattern) {
        return pattern.replaceAll("\\{[^/]+}", "HW-000001");
    }
}
