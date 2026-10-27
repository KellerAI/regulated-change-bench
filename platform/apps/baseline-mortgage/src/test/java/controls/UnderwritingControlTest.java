package controls;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import mortgage.Application;
import mortgage.Decision;
import mortgage.Policy;
import mortgage.Underwriting;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("control")
class UnderwritingControlTest {

    /** With this income, each dollar of monthly payments and debts is 0.01 percentage points of DTI. */
    private static final BigDecimal ANNUAL_INCOME = new BigDecimal("120000");
    private static final BigDecimal APPRAISED_VALUE = new BigDecimal("1000000");
    private static final BigDecimal LOAN_PER_LTV_POINT = new BigDecimal("10000");
    private static final int DTI_MAX_BASIS_POINTS = 10_000;
    private static final int LTV_MIN = 50;
    private static final int LTV_MAX = 110;
    private static final int MAX_REPORTED = 20;

    @Test
    @Control(obligation = "CRD-1", coverage = "exhaustive", domain = "mortgage.dti_ltv_grid")
    void autoApproveGridMatchesPolicy() {
        Map<String, Object> params = PolicyFiles.params();
        BigDecimal approvedDti = PolicyFiles.decimal(params, "mortgage.dti_max_percent");
        BigDecimal approvedLtv = PolicyFiles.decimal(params, "mortgage.ltv_max_percent");
        assertEquals(0, Policy.DTI_MAX_PERCENT.compareTo(approvedDti), "DTI_MAX_PERCENT differs from the approved " + approvedDti);
        assertEquals(0, Policy.LTV_MAX_PERCENT.compareTo(approvedLtv), "LTV_MAX_PERCENT differs from the approved " + approvedLtv);

        Underwriting underwriting = new Underwriting();
        List<String> violations = new ArrayList<>();
        int checked = 0;
        for (int basisPoints = 0; basisPoints <= DTI_MAX_BASIS_POINTS; basisPoints++) {
            BigDecimal dti = BigDecimal.valueOf(basisPoints, 2);
            BigDecimal payment = BigDecimal.valueOf(basisPoints / 2);
            BigDecimal otherDebt = BigDecimal.valueOf(basisPoints - basisPoints / 2);
            for (int ltv = LTV_MIN; ltv <= LTV_MAX; ltv++) {
                BigDecimal loan = LOAN_PER_LTV_POINT.multiply(BigDecimal.valueOf(ltv));
                Application application = new Application(loan, APPRAISED_VALUE, ANNUAL_INCOME, otherDebt, payment);
                boolean eligible = underwriting.decide(application).outcome() == Decision.Outcome.AUTO_APPROVE_ELIGIBLE;
                boolean expected = dti.compareTo(approvedDti) <= 0 && BigDecimal.valueOf(ltv).compareTo(approvedLtv) <= 0;
                if (eligible != expected && violations.size() < MAX_REPORTED) {
                    violations.add("DTI " + dti + "% LTV " + ltv + "%: eligible=" + eligible);
                }
                checked++;
            }
        }
        assertEquals((DTI_MAX_BASIS_POINTS + 1) * (LTV_MAX - LTV_MIN + 1), checked);
        assertTrue(violations.isEmpty(), "auto-approval differs from credit policy: " + violations);
    }
}
