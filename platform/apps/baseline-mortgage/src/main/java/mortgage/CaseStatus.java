package mortgage;

/**
 * Case lifecycle: DRAFT -> SUBMITTED or REFERRED -> APPROVED or DECLINED -> CLOSED,
 * with WITHDRAWN reachable from any active state.
 */
public enum CaseStatus {
    DRAFT,
    SUBMITTED,
    REFERRED,
    APPROVED,
    DECLINED,
    CLOSED,
    WITHDRAWN;

    /** Active cases still count towards duplicate-application checks. */
    public boolean isActive() {
        return this == DRAFT || this == SUBMITTED || this == REFERRED || this == APPROVED;
    }

    public boolean awaitsDecision() {
        return this == SUBMITTED || this == REFERRED;
    }
}
