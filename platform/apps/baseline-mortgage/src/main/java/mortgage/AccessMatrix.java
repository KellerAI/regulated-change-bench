package mortgage;

import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

/** Role-based access. Only the pairs granted below are allowed; everything else is denied. */
public final class AccessMatrix {

    private static final Map<Role, Set<Action>> GRANTS = new EnumMap<>(Role.class);

    static {
        grant(Role.APPLICANT, Action.CREATE_CASE);
        grant(Role.APPLICANT, Action.EDIT_CASE);
        grant(Role.APPLICANT, Action.VIEW_CASE);
        grant(Role.APPLICANT, Action.SUBMIT_CASE);
        grant(Role.PROCESSOR, Action.CREATE_CASE);
        grant(Role.PROCESSOR, Action.EDIT_CASE);
        grant(Role.PROCESSOR, Action.VIEW_CASE);
        grant(Role.PROCESSOR, Action.VIEW_NPI);
        grant(Role.PROCESSOR, Action.SUBMIT_CASE);
        grant(Role.UNDERWRITER, Action.EDIT_CASE);
        grant(Role.UNDERWRITER, Action.VIEW_CASE);
        grant(Role.UNDERWRITER, Action.VIEW_NPI);
        grant(Role.UNDERWRITER, Action.SUBMIT_CASE);
        grant(Role.UNDERWRITER, Action.APPROVE_CREDIT);
        grant(Role.UNDERWRITER, Action.DECLINE_CREDIT);
        grant(Role.SENIOR_UNDERWRITER, Action.EDIT_CASE);
        grant(Role.SENIOR_UNDERWRITER, Action.VIEW_CASE);
        grant(Role.SENIOR_UNDERWRITER, Action.VIEW_NPI);
        grant(Role.SENIOR_UNDERWRITER, Action.SUBMIT_CASE);
        grant(Role.SENIOR_UNDERWRITER, Action.APPROVE_CREDIT);
        grant(Role.SENIOR_UNDERWRITER, Action.DECLINE_CREDIT);
        grant(Role.SENIOR_UNDERWRITER, Action.OVERRIDE_POLICY);
        grant(Role.AUDITOR, Action.VIEW_CASE);
        grant(Role.AUDITOR, Action.VIEW_AUDIT);
        grant(Role.ADMIN, Action.VIEW_CASE);
        grant(Role.ADMIN, Action.VIEW_AUDIT);
        grant(Role.ADMIN, Action.EXPORT_CASES);
        grant(Role.ADMIN, Action.MANAGE_USERS);
        grant(Role.ADMIN, Action.PURGE_NPI);
    }

    private AccessMatrix() {
    }

    private static void grant(Role role, Action action) {
        GRANTS.computeIfAbsent(role, key -> EnumSet.noneOf(Action.class)).add(action);
    }

    public static boolean isAllowed(Role role, Action action) {
        Set<Action> granted = GRANTS.get(role);
        return granted != null && granted.contains(action);
    }
}
