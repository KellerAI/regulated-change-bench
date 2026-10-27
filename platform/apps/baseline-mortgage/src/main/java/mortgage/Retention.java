package mortgage;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

/** NPI retention for cases that did not become loans. */
public final class Retention {

    private final Clock clock;

    public Retention(Clock clock) {
        this.clock = clock;
    }

    /** Declined or withdrawn cases lose their NPI once the retention period has passed, unless held. */
    public boolean isPurgeDue(LoanCase loanCase) {
        if (!isClosedOut(loanCase.status())) {
            return false;
        }
        if (loanCase.isLegalHold()) {
            return false;
        }
        if (loanCase.npiPurgedAt() != null) {
            return false;
        }
        return loanCase.statusChangedAt().isBefore(cutoff());
    }

    public void purge(LoanCase loanCase) {
        for (String field : NpiRegistry.FIELDS) {
            loanCase.removeApplicantField(field);
        }
        loanCase.markNpiPurged(clock.instant());
    }

    Instant cutoff() {
        ZonedDateTime now = ZonedDateTime.ofInstant(clock.instant(), ZoneOffset.UTC);
        return now.minusMonths(Policy.DECLINED_NPI_RETENTION_MONTHS).toInstant();
    }

    private static boolean isClosedOut(CaseStatus status) {
        return status == CaseStatus.DECLINED || status == CaseStatus.WITHDRAWN;
    }
}
