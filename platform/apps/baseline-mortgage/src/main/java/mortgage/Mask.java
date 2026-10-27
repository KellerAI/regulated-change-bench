package mortgage;

/** Masking for values that must not appear in logs, exports or case summaries. */
public final class Mask {

    private static final int VISIBLE_SUFFIX = 4;
    private static final int MIN_LENGTH_WITH_SUFFIX = 8;

    private Mask() {
    }

    /** Hides all but the last four characters. Short values are hidden completely. */
    public static String npi(String value) {
        if (value == null) {
            return "[none]";
        }
        if (value.length() < MIN_LENGTH_WITH_SUFFIX) {
            return "****";
        }
        int hidden = value.length() - VISIBLE_SUFFIX;
        return "*".repeat(hidden) + value.substring(hidden);
    }
}
