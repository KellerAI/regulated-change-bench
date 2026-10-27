package mortgage;

import java.util.Set;

/** Applicant fields classified as non-public personal information. */
public final class NpiRegistry {

    public static final Set<String> FIELDS = Set.of("ssn", "date_of_birth", "bank_account_number", "annual_income");

    private NpiRegistry() {
    }

    public static boolean isNpi(String field) {
        return FIELDS.contains(field);
    }
}
