package controls;

import static org.junit.jupiter.api.Assertions.assertTrue;

import mortgage.Actor;
import mortgage.Approvals;
import mortgage.CaseStatus;
import mortgage.LoanCase;
import mortgage.Role;
import mortgage.ServiceException;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("control")
class ApprovalsControlTest {

    private static final BigDecimal GRID_MAX = new BigDecimal("3000000");
    private static final BigDecimal GRID_STEP = new BigDecimal("1000");
    private static final int MAX_REPORTED = 20;

    private final Actor processor = ControlFixtures.actor("mc-processor", Role.PROCESSOR);

    @Test
    @Control(obligation = "MC-1", coverage = "exhaustive", domain = "mortgage.approver_roles_x_actor")
    void makerCannotCheck() {
        Map<String, Object> policy = PolicyFiles.accessPolicy();
        Map<String, Object> matrix = PolicyFiles.object(policy, "matrix");
        List<String> violations = new ArrayList<>();
        int combinations = 0;
        for (String roleName : PolicyFiles.strings(policy, "roles")) {
            Map<String, Object> approvedRow = PolicyFiles.object(matrix, roleName);
            Role role = Role.valueOf(roleName);
            if (Boolean.TRUE.equals(approvedRow.get("APPROVE_CREDIT"))) {
                checkApprove(role, violations);
                combinations++;
            }
            if (Boolean.TRUE.equals(approvedRow.get("OVERRIDE_POLICY"))) {
                checkOverride(role, violations);
                combinations++;
            }
        }
        assertTrue(combinations > 0, "approved policy has no approver roles");
        assertTrue(violations.isEmpty(), "maker-checker violations: " + violations);
    }

    @Test
    @Control(obligation = "LIM-1", coverage = "exhaustive", domain = "mortgage.approval_amount_grid")
    void authorityLimitsMatchPolicy() {
        Map<String, Object> params = PolicyFiles.params();
        BigDecimal underwriterLimit = PolicyFiles.decimal(params, "mortgage.underwriter_limit");
        BigDecimal seniorLimit = PolicyFiles.decimal(params, "mortgage.senior_limit");
        List<String> violations = new ArrayList<>();
        for (BigDecimal amount : amountGrid(underwriterLimit, seniorLimit)) {
            Approvals.Requirement expected = expectedRequirement(amount, underwriterLimit, seniorLimit);
            Approvals.Requirement actual = Approvals.requiredApprovals(amount);
            if (!expected.equals(actual)) {
                violations.add(amount + ": requires " + actual + ", approved " + expected);
            }
            checkApprovalsFor(amount, expected, violations);
            if (violations.size() > MAX_REPORTED) {
                break;
            }
        }
        assertTrue(violations.isEmpty(), "approval authority differs from policy: " + violations);
    }

    private void checkApprove(Role role, List<String> violations) {
        ControlFixtures fixtures = new ControlFixtures();
        Actor maker = ControlFixtures.actor("mc-maker", role);
        Actor checker = ControlFixtures.actor("mc-checker", role);
        LoanCase loanCase = fixtures.readyCase(
                processor,
                ControlFixtures.applicant("Ines Calloway", "900-71-4410", "1983-09-30", "007144100021", "120000"),
                ControlFixtures.loan("200000", "400000", "500"));
        fixtures.service.submit(maker, loanCase.id());
        if (attempt(() -> fixtures.service.approve(maker, loanCase.id()))) {
            violations.add(role + " preparer approved their own case");
            return;
        }
        if (!attempt(() -> fixtures.service.approve(checker, loanCase.id()))) {
            violations.add(role + " independent approver was refused");
            return;
        }
        if (fixtures.service.view(checker, loanCase.id()).status() != CaseStatus.APPROVED) {
            violations.add(role + " independent approval did not approve the case");
        }
    }

    private void checkOverride(Role role, List<String> violations) {
        ControlFixtures fixtures = new ControlFixtures();
        Actor maker = ControlFixtures.actor("mc-maker", role);
        Actor checker = ControlFixtures.actor("mc-checker", role);
        LoanCase loanCase = fixtures.readyCase(
                processor,
                ControlFixtures.applicant("Oren Ashdown", "900-71-5523", "1977-01-18", "007155230087", "120000"),
                ControlFixtures.loan("200000", "400000", "3500"));
        fixtures.service.submit(maker, loanCase.id());
        if (attempt(() -> fixtures.service.override(maker, loanCase.id(), "Compensating reserves"))) {
            violations.add(role + " preparer overrode policy on their own case");
            return;
        }
        if (!attempt(() -> fixtures.service.override(checker, loanCase.id(), "Compensating reserves"))) {
            violations.add(role + " independent override was refused");
            return;
        }
        if (fixtures.service.view(checker, loanCase.id()).status() != CaseStatus.APPROVED) {
            violations.add(role + " independent override did not approve the case");
        }
    }

    private static boolean attempt(Runnable operation) {
        try {
            operation.run();
            return true;
        } catch (ServiceException refused) {
            return false;
        }
    }

    private static List<BigDecimal> amountGrid(BigDecimal underwriterLimit, BigDecimal seniorLimit) {
        TreeSet<BigDecimal> amounts = new TreeSet<>();
        for (BigDecimal amount = BigDecimal.ZERO; amount.compareTo(GRID_MAX) <= 0; amount = amount.add(GRID_STEP)) {
            amounts.add(amount);
        }
        for (BigDecimal limit : List.of(underwriterLimit, seniorLimit)) {
            amounts.add(limit.subtract(BigDecimal.ONE));
            amounts.add(limit);
            amounts.add(limit.add(BigDecimal.ONE));
        }
        return new ArrayList<>(amounts);
    }

    private static Approvals.Requirement expectedRequirement(BigDecimal amount, BigDecimal underwriterLimit, BigDecimal seniorLimit) {
        if (amount.compareTo(underwriterLimit) <= 0) {
            return new Approvals.Requirement(Role.UNDERWRITER, 1);
        }
        if (amount.compareTo(seniorLimit) <= 0) {
            return new Approvals.Requirement(Role.SENIOR_UNDERWRITER, 1);
        }
        return new Approvals.Requirement(Role.SENIOR_UNDERWRITER, 2);
    }

    /** Walks the approvals an amount needs: who may approve, when approval completes, distinct seniors. */
    private static void checkApprovalsFor(BigDecimal amount, Approvals.Requirement expected, List<String> violations) {
        Actor underwriter = ControlFixtures.actor("lim-underwriter", Role.UNDERWRITER);
        Actor senior = ControlFixtures.actor("lim-senior", Role.SENIOR_UNDERWRITER);
        Actor secondSenior = ControlFixtures.actor("lim-senior-2", Role.SENIOR_UNDERWRITER);
        boolean underwriterAllowed = expected.minimumRole() == Role.UNDERWRITER;
        Boolean underwriterResult = approveOrNull(caseFor(amount), underwriter);
        if ((underwriterResult != null) != underwriterAllowed) {
            violations.add(amount + ": underwriter approval accepted=" + (underwriterResult != null));
        }
        if (underwriterResult != null && underwriterAllowed && !underwriterResult) {
            violations.add(amount + ": one underwriter approval did not complete");
        }
        LoanCase seniorCase = caseFor(amount);
        Boolean first = approveOrNull(seniorCase, senior);
        if (first == null || first != (expected.approvers() == 1)) {
            violations.add(amount + ": first senior approval complete=" + first);
            return;
        }
        if (expected.approvers() == 2) {
            if (approveOrNull(seniorCase, senior) != null) {
                violations.add(amount + ": the same senior counted twice");
            }
            if (!Boolean.TRUE.equals(approveOrNull(seniorCase, secondSenior))) {
                violations.add(amount + ": a second distinct senior did not complete approval");
            }
        }
    }

    private static Boolean approveOrNull(LoanCase loanCase, Actor actor) {
        try {
            return Approvals.approve(loanCase, actor);
        } catch (ServiceException refused) {
            return null;
        }
    }

    private static LoanCase caseFor(BigDecimal amount) {
        LoanCase loanCase = new LoanCase("HW-LIM", null, "lim-processor", ControlFixtures.START);
        loanCase.setLoanAmount(amount);
        loanCase.setPreparedBy("lim-preparer");
        return loanCase;
    }
}
