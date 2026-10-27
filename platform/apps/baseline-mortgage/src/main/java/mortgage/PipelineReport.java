package mortgage;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

/** Case counts and volumes by status, with a count of cases waiting too long for a decision. */
public record PipelineReport(Instant asOf, List<Row> rows, int staleCases) {

    static final Duration STALE_AFTER = Duration.ofDays(5);

    /** One status line of the report. */
    public record Row(CaseStatus status, int count, BigDecimal totalLoanAmount) {
    }

    public PipelineReport {
        rows = List.copyOf(rows);
    }

    public static PipelineReport build(Collection<LoanCase> cases, Instant asOf) {
        List<Row> rows = new ArrayList<>();
        for (CaseStatus status : CaseStatus.values()) {
            rows.add(rowFor(status, cases));
        }
        return new PipelineReport(asOf, rows, countStale(cases, asOf));
    }

    public Row row(CaseStatus status) {
        for (Row row : rows) {
            if (row.status() == status) {
                return row;
            }
        }
        throw new IllegalArgumentException("No row for " + status);
    }

    private static Row rowFor(CaseStatus status, Collection<LoanCase> cases) {
        int count = 0;
        BigDecimal total = BigDecimal.ZERO;
        for (LoanCase loanCase : cases) {
            if (loanCase.status() == status) {
                count++;
                total = total.add(loanCase.loanAmount());
            }
        }
        return new Row(status, count, total);
    }

    private static int countStale(Collection<LoanCase> cases, Instant asOf) {
        int stale = 0;
        for (LoanCase loanCase : cases) {
            Duration waiting = Duration.between(loanCase.statusChangedAt(), asOf);
            if (loanCase.status().awaitsDecision() && waiting.compareTo(STALE_AFTER) > 0) {
                stale++;
            }
        }
        return stale;
    }
}
