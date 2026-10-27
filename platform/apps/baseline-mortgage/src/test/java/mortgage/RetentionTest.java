package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import org.junit.jupiter.api.Test;

class RetentionTest {

    private final TestClock clock = new TestClock(Fixtures.START);
    private final Retention retention = new Retention(clock);

    @Test
    void withdrawnCasesArePurgedAfterTheRetentionPeriod() {
        LoanCase loanCase = closedOut(CaseStatus.WITHDRAWN);
        clock.advanceMonths(Policy.DECLINED_NPI_RETENTION_MONTHS + 1);
        assertTrue(retention.isPurgeDue(loanCase));
    }

    @Test
    void approvedAndClosedCasesAreNeverPurgedHere() {
        LoanCase approved = closedOut(CaseStatus.APPROVED);
        LoanCase closed = closedOut(CaseStatus.CLOSED);
        clock.advanceMonths(120);
        assertFalse(retention.isPurgeDue(approved));
        assertFalse(retention.isPurgeDue(closed));
    }

    @Test
    void recentDeclinesAreKept() {
        LoanCase loanCase = closedOut(CaseStatus.DECLINED);
        clock.advanceMonths(Policy.DECLINED_NPI_RETENTION_MONTHS - 1);
        assertFalse(retention.isPurgeDue(loanCase));
    }

    @Test
    void purgeRemovesOnlyNpiAndIsNotRepeated() {
        LoanCase loanCase = closedOut(CaseStatus.DECLINED);
        clock.advanceMonths(Policy.DECLINED_NPI_RETENTION_MONTHS + 2);
        retention.purge(loanCase);
        assertNull(loanCase.applicantField("ssn"));
        assertNull(loanCase.applicantField("annual_income"));
        assertEquals("Lena Marsh", loanCase.applicantField("full_name"));
        assertEquals(clock.instant(), loanCase.npiPurgedAt());
        assertFalse(retention.isPurgeDue(loanCase));
    }

    private LoanCase closedOut(CaseStatus status) {
        LoanCase loanCase = new LoanCase("HW-000020", null, "proc-ada", clock.instant());
        for (Map.Entry<String, String> field : Fixtures.applicant("900-20-0020").entrySet()) {
            loanCase.putApplicantField(field.getKey(), field.getValue());
        }
        loanCase.moveTo(status, clock.instant());
        return loanCase;
    }
}
