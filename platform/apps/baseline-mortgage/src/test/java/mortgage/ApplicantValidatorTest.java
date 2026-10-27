package mortgage;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import org.junit.jupiter.api.Test;

class ApplicantValidatorTest {

    private final AppLog log = new AppLog(new TestClock(Fixtures.START));
    private final ApplicantValidator validator = new ApplicantValidator(log);

    @Test
    void acceptsAWellFormedApplicant() {
        assertDoesNotThrow(() -> validator.validate("new case", Fixtures.applicant("900-12-3456")));
    }

    @Test
    void rejectsUnknownFields() {
        assertThrows(ServiceException.class, () -> validator.validate("HW-000001", Map.of("favourite_colour", "teal")));
    }

    @Test
    void rejectsMalformedNpiWithoutLoggingIt() {
        assertThrows(ServiceException.class, () -> validator.validate("HW-000001", Map.of("ssn", "900123456")));
        assertThrows(ServiceException.class, () -> validator.validate("HW-000001", Map.of("bank_account_number", "12-34-5678")));
        assertThrows(ServiceException.class, () -> validator.validate("HW-000001", Map.of("date_of_birth", "29/02/1988")));
        assertThrows(ServiceException.class, () -> validator.validate("HW-000001", Map.of("annual_income", "lots")));
        String logged = String.join("\n", log.lines());
        assertTrue(logged.contains("HW-000001"));
        assertFalse(logged.contains("900123456"));
        assertFalse(logged.contains("12-34-5678"));
        assertFalse(logged.contains("29/02/1988"));
    }

    @Test
    void rejectsBadFlagsAndOverLongText() {
        assertThrows(ServiceException.class, () -> validator.validate("HW-000001", Map.of("self_employed", "yes")));
        assertThrows(ServiceException.class, () -> validator.validate("HW-000001", Map.of("employer", "x".repeat(201))));
    }
}
