package mortgage;

import java.util.List;

/** The applicant fields a case can hold. */
public final class ApplicantFields {

    public static final List<String> ALL = List.of(
            "full_name",
            "email",
            "phone",
            "employer",
            "self_employed",
            "ssn",
            "date_of_birth",
            "bank_account_number",
            "annual_income");

    public static final List<String> REQUIRED_FOR_SUBMIT = List.of(
            "full_name",
            "ssn",
            "date_of_birth",
            "annual_income");

    private ApplicantFields() {
    }
}
