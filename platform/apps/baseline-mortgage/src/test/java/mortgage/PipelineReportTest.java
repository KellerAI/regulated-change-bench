package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class PipelineReportTest {

    private static final Instant NOW = Fixtures.START;

    @Test
    void countsAndTotalsByStatus() {
        PipelineReport report = PipelineReport.build(List.of(
                caseIn(CaseStatus.SUBMITTED, "200000", NOW),
                caseIn(CaseStatus.SUBMITTED, "150000", NOW),
                caseIn(CaseStatus.APPROVED, "500000", NOW)), NOW);
        assertEquals(2, report.row(CaseStatus.SUBMITTED).count());
        assertEquals(new BigDecimal("350000"), report.row(CaseStatus.SUBMITTED).totalLoanAmount());
        assertEquals(1, report.row(CaseStatus.APPROVED).count());
        assertEquals(0, report.row(CaseStatus.DRAFT).count());
        assertEquals(CaseStatus.values().length, report.rows().size());
    }

    @Test
    void flagsCasesWaitingTooLongForADecision() {
        Instant longAgo = NOW.minus(Duration.ofDays(6));
        PipelineReport report = PipelineReport.build(List.of(
                caseIn(CaseStatus.REFERRED, "300000", longAgo),
                caseIn(CaseStatus.SUBMITTED, "300000", NOW.minus(Duration.ofDays(2))),
                caseIn(CaseStatus.APPROVED, "300000", longAgo)), NOW);
        assertEquals(1, report.staleCases());
    }

    private static LoanCase caseIn(CaseStatus status, String amount, Instant since) {
        LoanCase loanCase = new LoanCase("HW-000050", null, "proc-ada", since);
        loanCase.setLoanAmount(new BigDecimal(amount));
        loanCase.moveTo(status, since);
        return loanCase;
    }
}
