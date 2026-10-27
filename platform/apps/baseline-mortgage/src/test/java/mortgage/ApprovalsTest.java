package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class ApprovalsTest {

    @Test
    void requirementGrowsWithTheAmount() {
        assertEquals(new Approvals.Requirement(Role.UNDERWRITER, 1), Approvals.requiredApprovals(new BigDecimal("350000")));
        assertEquals(new Approvals.Requirement(Role.SENIOR_UNDERWRITER, 1), Approvals.requiredApprovals(new BigDecimal("900000")));
        assertEquals(new Approvals.Requirement(Role.SENIOR_UNDERWRITER, 2), Approvals.requiredApprovals(new BigDecimal("2000000")));
    }

    @Test
    void seniorsMayApproveWhatUnderwritersMay() {
        Approvals.Requirement requirement = Approvals.requiredApprovals(new BigDecimal("100000"));
        assertTrue(requirement.allows(Role.SENIOR_UNDERWRITER));
        assertFalse(requirement.allows(Role.PROCESSOR));
    }

    @Test
    void oneUnderwriterApprovesASmallLoan() {
        assertTrue(Approvals.approve(loan("250000"), Fixtures.UNDERWRITER));
    }

    @Test
    void underwritersCannotApproveAboveTheirLimit() {
        ServiceException refused = assertThrows(ServiceException.class, () -> Approvals.approve(loan("750000"), Fixtures.UNDERWRITER));
        assertEquals(ServiceException.AUTHORITY, refused.code());
    }

    @Test
    void largeLoansNeedTwoDistinctSeniors() {
        LoanCase loanCase = loan("2500000");
        assertFalse(Approvals.approve(loanCase, Fixtures.SENIOR));
        ServiceException again = assertThrows(ServiceException.class, () -> Approvals.approve(loanCase, Fixtures.SENIOR));
        assertEquals(ServiceException.DUPLICATE, again.code());
        assertTrue(Approvals.approve(loanCase, Fixtures.SECOND_SENIOR));
    }

    @Test
    void thePreparerCannotApprove() {
        LoanCase loanCase = loan("250000");
        loanCase.setPreparedBy(Fixtures.UNDERWRITER.userId());
        ServiceException refused = assertThrows(ServiceException.class, () -> Approvals.approve(loanCase, Fixtures.UNDERWRITER));
        assertEquals(ServiceException.MAKER_CHECKER, refused.code());
    }

    private static LoanCase loan(String amount) {
        LoanCase loanCase = new LoanCase("HW-000010", null, "proc-ada", Fixtures.START);
        loanCase.setLoanAmount(new BigDecimal(amount));
        loanCase.setPreparedBy("proc-ada");
        return loanCase;
    }
}
