package mortgage;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

/** Automated underwriting against the credit policy in {@link Policy}. */
public final class Underwriting {

    private static final BigDecimal HUNDRED = new BigDecimal("100");
    private static final BigDecimal PERCENT_TIMES_MONTHS = new BigDecimal("1200");
    private static final int RATIO_SCALE = 4;

    public Decision decide(Application application) {
        List<String> missing = missingInputs(application);
        if (!missing.isEmpty()) {
            return new Decision(Decision.Outcome.REFER, null, null, missing);
        }
        BigDecimal dti = debtToIncomePercent(application);
        BigDecimal ltv = loanToValuePercent(application.loanAmount(), application.appraisedValue());
        List<String> hardStops = hardStops(dti, ltv);
        if (!hardStops.isEmpty()) {
            return new Decision(Decision.Outcome.DECLINE, dti, ltv, hardStops);
        }
        boolean dtiWithinPolicy = dti.compareTo(Policy.DTI_MAX_PERCENT) <= 0;
        boolean ltvWithinPolicy = ltv.compareTo(Policy.LTV_MAX_PERCENT) <= 0;
        if (dtiWithinPolicy && ltvWithinPolicy) {
            return new Decision(Decision.Outcome.AUTO_APPROVE_ELIGIBLE, dti, ltv, List.of());
        }
        return new Decision(Decision.Outcome.REFER, dti, ltv, referReasons(dtiWithinPolicy, ltvWithinPolicy));
    }

    /** (proposed payment + monthly debt) / (annual income / 12), as a percentage. */
    public static BigDecimal debtToIncomePercent(Application application) {
        BigDecimal monthlyObligations = application.proposedMonthlyPayment().add(application.monthlyDebt());
        BigDecimal scaled = monthlyObligations.multiply(PERCENT_TIMES_MONTHS);
        return scaled.divide(application.annualIncome(), RATIO_SCALE, RoundingMode.HALF_UP);
    }

    /** Loan amount / appraised value, as a percentage. */
    public static BigDecimal loanToValuePercent(BigDecimal loanAmount, BigDecimal appraisedValue) {
        return loanAmount.multiply(HUNDRED).divide(appraisedValue, RATIO_SCALE, RoundingMode.HALF_UP);
    }

    private static List<String> missingInputs(Application application) {
        List<String> missing = new ArrayList<>();
        if (!isPositive(application.annualIncome())) {
            missing.add("INCOME_NOT_VERIFIED");
        }
        if (!isPositive(application.appraisedValue())) {
            missing.add("APPRAISAL_MISSING");
        }
        if (!isPositive(application.loanAmount())) {
            missing.add("LOAN_AMOUNT_MISSING");
        }
        if (application.proposedMonthlyPayment() == null) {
            missing.add("PAYMENT_NOT_QUOTED");
        }
        return missing;
    }

    private static List<String> hardStops(BigDecimal dti, BigDecimal ltv) {
        List<String> reasons = new ArrayList<>();
        if (dti.compareTo(Policy.DTI_DECLINE_PERCENT) > 0) {
            reasons.add("DTI_HARD_STOP");
        }
        if (ltv.compareTo(Policy.LTV_DECLINE_PERCENT) > 0) {
            reasons.add("LTV_HARD_STOP");
        }
        return reasons;
    }

    private static List<String> referReasons(boolean dtiWithinPolicy, boolean ltvWithinPolicy) {
        List<String> reasons = new ArrayList<>();
        if (!dtiWithinPolicy) {
            reasons.add("DTI_ABOVE_POLICY");
        }
        if (!ltvWithinPolicy) {
            reasons.add("LTV_ABOVE_POLICY");
        }
        return reasons;
    }

    private static boolean isPositive(BigDecimal value) {
        return value != null && value.signum() > 0;
    }
}
