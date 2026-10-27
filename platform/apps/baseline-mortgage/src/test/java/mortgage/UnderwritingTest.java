package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class UnderwritingTest {

    private final Underwriting underwriting = new Underwriting();

    @Test
    void withinPolicyIsEligibleForAutoApproval() {
        Decision decision = underwriting.decide(application("300000", "400000", "96000", "600", "1847.15"));
        assertEquals(Decision.Outcome.AUTO_APPROVE_ELIGIBLE, decision.outcome());
        assertEquals(new BigDecimal("30.5894"), decision.dtiPercent());
        assertEquals(new BigDecimal("75.0000"), decision.ltvPercent());
    }

    @Test
    void highDebtIsReferred() {
        Decision decision = underwriting.decide(application("300000", "400000", "96000", "1500", "1847.15"));
        assertEquals(Decision.Outcome.REFER, decision.outcome());
        assertEquals(List.of("DTI_ABOVE_POLICY"), decision.reasons());
    }

    @Test
    void highLoanToValueIsReferred() {
        Decision decision = underwriting.decide(application("380000", "400000", "150000", "0", "2433.18"));
        assertEquals(Decision.Outcome.REFER, decision.outcome());
        assertEquals(List.of("LTV_ABOVE_POLICY"), decision.reasons());
    }

    @Test
    void hardStopsAreDeclined() {
        Decision decision = underwriting.decide(application("450000", "400000", "60000", "1500", "2881.40"));
        assertEquals(Decision.Outcome.DECLINE, decision.outcome());
        assertEquals(List.of("DTI_HARD_STOP", "LTV_HARD_STOP"), decision.reasons());
    }

    @Test
    void theLimitsThemselvesAreWithinPolicy() {
        Decision decision = underwriting.decide(application("90000", "100000", "120000", "0", "4000"));
        assertEquals(new BigDecimal("40.0000"), decision.dtiPercent());
        assertEquals(new BigDecimal("90.0000"), decision.ltvPercent());
        assertEquals(Decision.Outcome.AUTO_APPROVE_ELIGIBLE, decision.outcome());
    }

    @Test
    void missingInputsAreReferredWithoutRatios() {
        Application incomplete = new Application(new BigDecimal("200000"), new BigDecimal("400000"), null, BigDecimal.ZERO, null);
        Decision decision = underwriting.decide(incomplete);
        assertEquals(Decision.Outcome.REFER, decision.outcome());
        assertEquals(List.of("INCOME_NOT_VERIFIED", "PAYMENT_NOT_QUOTED"), decision.reasons());
        assertNull(decision.dtiPercent());
    }

    private static Application application(String loan, String appraised, String income, String debt, String payment) {
        return new Application(
                new BigDecimal(loan),
                new BigDecimal(appraised),
                new BigDecimal(income),
                new BigDecimal(debt),
                new BigDecimal(payment));
    }
}
