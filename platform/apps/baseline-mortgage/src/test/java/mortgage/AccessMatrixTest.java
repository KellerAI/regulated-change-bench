package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.EnumSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class AccessMatrixTest {

    @Test
    void applicantsWorkOnTheirApplicationOnly() {
        assertTrue(AccessMatrix.isAllowed(Role.APPLICANT, Action.CREATE_CASE));
        assertTrue(AccessMatrix.isAllowed(Role.APPLICANT, Action.SUBMIT_CASE));
        assertFalse(AccessMatrix.isAllowed(Role.APPLICANT, Action.VIEW_NPI));
        assertFalse(AccessMatrix.isAllowed(Role.APPLICANT, Action.APPROVE_CREDIT));
    }

    @Test
    void onlySeniorUnderwritersOverridePolicy() {
        for (Role role : Role.values()) {
            assertEquals(role == Role.SENIOR_UNDERWRITER, AccessMatrix.isAllowed(role, Action.OVERRIDE_POLICY), role.name());
        }
    }

    @Test
    void underwritersDecideCredit() {
        assertTrue(AccessMatrix.isAllowed(Role.UNDERWRITER, Action.APPROVE_CREDIT));
        assertTrue(AccessMatrix.isAllowed(Role.UNDERWRITER, Action.DECLINE_CREDIT));
        assertFalse(AccessMatrix.isAllowed(Role.PROCESSOR, Action.APPROVE_CREDIT));
    }

    @Test
    void adminRunsTheSystemButHasNoNpiAccess() {
        assertTrue(AccessMatrix.isAllowed(Role.ADMIN, Action.MANAGE_USERS));
        assertTrue(AccessMatrix.isAllowed(Role.ADMIN, Action.PURGE_NPI));
        assertFalse(AccessMatrix.isAllowed(Role.ADMIN, Action.VIEW_NPI));
    }

    @Test
    void auditorsReadCasesAndTheAuditTrail() {
        Set<Action> granted = EnumSet.noneOf(Action.class);
        for (Action action : Action.values()) {
            if (AccessMatrix.isAllowed(Role.AUDITOR, action)) {
                granted.add(action);
            }
        }
        assertEquals(EnumSet.of(Action.VIEW_CASE, Action.VIEW_AUDIT), granted);
    }

    @Test
    void privilegedActionsAreTheSensitiveOnes() {
        Set<Action> privileged = EnumSet.noneOf(Action.class);
        for (Action action : Action.values()) {
            if (action.isPrivileged()) {
                privileged.add(action);
            }
        }
        Set<Action> expected = EnumSet.of(
                Action.VIEW_NPI,
                Action.APPROVE_CREDIT,
                Action.OVERRIDE_POLICY,
                Action.EXPORT_CASES,
                Action.MANAGE_USERS,
                Action.PURGE_NPI);
        assertEquals(expected, privileged);
    }

    @Test
    void viewingIsNotStateChanging() {
        assertFalse(Action.VIEW_CASE.isStateChanging());
        assertFalse(Action.VIEW_AUDIT.isStateChanging());
        assertTrue(Action.EDIT_CASE.isStateChanging());
    }
}
