package mortgage;

/**
 * Operations a caller can be granted.
 *
 * <p>Each action declares whether it changes case or system state and whether it is
 * privileged. Privileged actions need step-up MFA and use the shorter idle timeout.
 */
public enum Action {
    CREATE_CASE(true, false),
    EDIT_CASE(true, false),
    VIEW_CASE(false, false),
    VIEW_NPI(false, true),
    SUBMIT_CASE(true, false),
    APPROVE_CREDIT(true, true),
    DECLINE_CREDIT(true, false),
    OVERRIDE_POLICY(true, true),
    EXPORT_CASES(false, true),
    MANAGE_USERS(true, true),
    VIEW_AUDIT(false, false),
    PURGE_NPI(true, true);

    private final boolean stateChanging;
    private final boolean privileged;

    Action(boolean stateChanging, boolean privileged) {
        this.stateChanging = stateChanging;
        this.privileged = privileged;
    }

    public boolean isStateChanging() {
        return stateChanging;
    }

    public boolean isPrivileged() {
        return privileged;
    }
}
