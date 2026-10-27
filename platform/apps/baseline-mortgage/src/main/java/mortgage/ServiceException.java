package mortgage;

/** A rejected service operation. The code is stable and safe to return to clients. */
public final class ServiceException extends RuntimeException {

    public static final String FORBIDDEN = "forbidden";
    public static final String NOT_FOUND = "not_found";
    public static final String INVALID_STATE = "invalid_state";
    public static final String VALIDATION = "validation";
    public static final String MAKER_CHECKER = "maker_checker";
    public static final String AUTHORITY = "authority";
    public static final String DUPLICATE = "duplicate";

    private static final long serialVersionUID = 1L;

    private final String code;

    public ServiceException(String code, String message) {
        super(message);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
