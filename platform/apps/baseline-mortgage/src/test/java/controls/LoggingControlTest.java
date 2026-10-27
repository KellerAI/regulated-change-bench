package controls;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import mortgage.Actor;
import mortgage.LoanCase;
import mortgage.LoanRequest;
import mortgage.NpiRegistry;
import mortgage.Role;
import mortgage.ServiceException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("control")
class LoggingControlTest {

    @Test
    @Control(obligation = "LOG-1", coverage = "sample", domain = "mortgage.sampled_log_flows")
    void sampledFlowsDoNotLogNpi() {
        ControlFixtures fixtures = new ControlFixtures();
        Actor processor = ControlFixtures.actor("log-processor", Role.PROCESSOR);
        Actor underwriter = ControlFixtures.actor("log-underwriter", Role.UNDERWRITER);
        Actor admin = ControlFixtures.actor("log-admin", Role.ADMIN);
        Map<String, String> applicant = ControlFixtures.applicant("Rowan Ellery", "900-41-7733", "1979-06-14", "004417730091", "131500");
        LoanRequest loan = ControlFixtures.loan("200000", "400000", "500");

        LoanCase loanCase = fixtures.readyCase(processor, applicant, loan);
        fixtures.service.submit(processor, loanCase.id());
        fixtures.service.approve(underwriter, loanCase.id());
        int linesBeforeDuplicate = fixtures.log.lines().size();
        assertThrows(ServiceException.class, () -> fixtures.service.create(processor, applicant, loan));
        assertTrue(fixtures.log.lines().size() > linesBeforeDuplicate, "the duplicate-application error path should be logged");
        fixtures.service.export(admin);

        List<String> leaks = new ArrayList<>();
        for (String line : fixtures.log.lines()) {
            for (String field : NpiRegistry.FIELDS) {
                String value = applicant.get(field);
                if (value != null && line.contains(value)) {
                    leaks.add(field + " in: " + line);
                }
            }
        }
        assertTrue(leaks.isEmpty(), "NPI reached the application log: " + leaks);
    }
}
