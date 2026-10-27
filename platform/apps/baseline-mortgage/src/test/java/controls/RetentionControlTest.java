package controls;

import static org.junit.jupiter.api.Assertions.assertTrue;

import mortgage.Actor;
import mortgage.LoanCase;
import mortgage.NpiRegistry;
import mortgage.Role;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("control")
class RetentionControlTest {

    private final Actor processor = ControlFixtures.actor("ret-processor", Role.PROCESSOR);
    private final Actor underwriter = ControlFixtures.actor("ret-underwriter", Role.UNDERWRITER);
    private final Actor admin = ControlFixtures.actor("ret-admin", Role.ADMIN);

    @Test
    @Control(obligation = "RET-1", coverage = "sample", domain = "mortgage.sampled_retention_cases")
    void sampledPurgeRespectsHold() {
        ControlFixtures fixtures = new ControlFixtures();
        LoanCase expired = declinedCase(fixtures, "Alder Quinn", "900-52-1184");
        LoanCase held = declinedCase(fixtures, "Briar Holm", "900-52-2291");
        fixtures.service.setLegalHold(admin, held.id(), true);
        fixtures.clock.advanceMonths(27);
        LoanCase recent = declinedCase(fixtures, "Cass Varden", "900-52-3307");
        fixtures.clock.advanceMonths(3);

        fixtures.service.purgeExpiredNpi(admin);

        List<String> violations = new ArrayList<>();
        expectNpi(fixtures, expired.id(), false, violations);
        expectNpi(fixtures, held.id(), true, violations);
        expectNpi(fixtures, recent.id(), true, violations);
        assertTrue(violations.isEmpty(), "retention purge problems: " + violations);
    }

    private LoanCase declinedCase(ControlFixtures fixtures, String name, String ssn) {
        LoanCase loanCase = fixtures.readyCase(
                processor,
                ControlFixtures.applicant(name, ssn, "1990-04-21", "005201184400", "92000"),
                ControlFixtures.loan("380000", "400000", "2600"));
        fixtures.service.submit(processor, loanCase.id());
        return fixtures.service.decline(underwriter, loanCase.id(), "Applicant asked us to stop");
    }

    private static void expectNpi(ControlFixtures fixtures, String caseId, boolean retained, List<String> violations) {
        LoanCase loanCase = fixtures.store.find(caseId).orElseThrow();
        for (String field : NpiRegistry.FIELDS) {
            boolean present = loanCase.applicantField(field) != null;
            if (present != retained) {
                violations.add(caseId + " " + field + (retained ? " was purged" : " was kept"));
            }
        }
    }
}
