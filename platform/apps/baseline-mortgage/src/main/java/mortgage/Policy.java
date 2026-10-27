package mortgage;

import java.math.BigDecimal;

/**
 * Approved credit, authority, session and retention parameters.
 * Changes here go through the credit-policy change process.
 */
public final class Policy {

    public static final BigDecimal DTI_MAX_PERCENT = new BigDecimal("40");
    public static final BigDecimal LTV_MAX_PERCENT = new BigDecimal("90");
    public static final BigDecimal DTI_DECLINE_PERCENT = new BigDecimal("50");
    public static final BigDecimal LTV_DECLINE_PERCENT = new BigDecimal("100");
    public static final BigDecimal UNDERWRITER_LIMIT = new BigDecimal("500000");
    public static final BigDecimal SENIOR_LIMIT = new BigDecimal("1500000");
    public static final int PRIVILEGED_IDLE_MINUTES = 15;
    public static final int STANDARD_IDLE_MINUTES = 30;
    public static final int AUDIT_RETENTION_YEARS = 7;
    public static final int DECLINED_NPI_RETENTION_MONTHS = 25;

    private Policy() {
    }
}
