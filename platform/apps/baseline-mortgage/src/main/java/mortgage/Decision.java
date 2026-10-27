package mortgage;

import java.math.BigDecimal;
import java.util.List;

/** The automated underwriting result for a case. Ratios are percentages; null when inputs were missing. */
public record Decision(Outcome outcome, BigDecimal dtiPercent, BigDecimal ltvPercent, List<String> reasons) {

    /** Automated underwriting outcomes. */
    public enum Outcome {
        AUTO_APPROVE_ELIGIBLE,
        REFER,
        DECLINE
    }

    public Decision {
        reasons = List.copyOf(reasons);
    }
}
