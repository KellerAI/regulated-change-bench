package mortgage;

import java.util.Map;
import java.util.regex.Pattern;

/** Format checks for applicant fields supplied on create and edit. */
public final class ApplicantValidator {

    private static final Pattern SSN_FORMAT = Pattern.compile("\\d{3}-\\d{2}-\\d{4}");
    private static final Pattern ACCOUNT_FORMAT = Pattern.compile("\\d{8,17}");
    private static final Pattern DATE_FORMAT = Pattern.compile("\\d{4}-\\d{2}-\\d{2}");
    private static final Pattern AMOUNT_FORMAT = Pattern.compile("\\d{1,9}(\\.\\d{1,2})?");
    private static final Pattern FLAG_FORMAT = Pattern.compile("true|false");
    private static final int MAX_TEXT_LENGTH = 200;

    private final AppLog log;

    public ApplicantValidator(AppLog log) {
        this.log = log;
    }

    public void validate(String caseRef, Map<String, String> fields) {
        for (Map.Entry<String, String> field : fields.entrySet()) {
            validateField(caseRef, field.getKey(), field.getValue());
        }
    }

    private void validateField(String caseRef, String name, String value) {
        if (!ApplicantFields.ALL.contains(name)) {
            log.warn("Unknown applicant field " + name + " on " + caseRef);
            throw invalid("Unknown applicant field: " + name);
        }
        if (value == null) {
            return;
        }
        switch (name) {
            case "ssn" -> checkSsn(caseRef, value);
            case "bank_account_number" -> checkAccountNumber(caseRef, value);
            case "date_of_birth" -> checkDateOfBirth(caseRef, value);
            case "annual_income" -> checkIncome(caseRef, value);
            case "self_employed" -> checkFlag(caseRef, value);
            default -> checkText(caseRef, name, value);
        }
    }

    private void checkSsn(String caseRef, String value) {
        if (!SSN_FORMAT.matcher(value).matches()) {
            log.warn("Rejected SSN " + Mask.npi(value) + " on " + caseRef);
            throw invalid("SSN must use the NNN-NN-NNNN format");
        }
    }

    private void checkAccountNumber(String caseRef, String value) {
        if (!ACCOUNT_FORMAT.matcher(value).matches()) {
            log.warn("Rejected bank account " + Mask.npi(value) + " on " + caseRef);
            throw invalid("Bank account number must be 8 to 17 digits");
        }
    }

    private void checkDateOfBirth(String caseRef, String value) {
        if (!DATE_FORMAT.matcher(value).matches()) {
            log.warn("Rejected date of birth " + Mask.npi(value) + " on " + caseRef);
            throw invalid("Date of birth must use the YYYY-MM-DD format");
        }
    }

    private void checkIncome(String caseRef, String value) {
        if (!AMOUNT_FORMAT.matcher(value).matches()) {
            log.warn("Rejected annual income " + Mask.npi(value) + " on " + caseRef);
            throw invalid("Annual income must be a plain amount");
        }
    }

    private void checkFlag(String caseRef, String value) {
        if (!FLAG_FORMAT.matcher(value).matches()) {
            log.warn("Rejected self_employed flag on " + caseRef);
            throw invalid("self_employed must be true or false");
        }
    }

    private void checkText(String caseRef, String name, String value) {
        if (value.length() > MAX_TEXT_LENGTH) {
            log.warn("Rejected over-long " + name + " on " + caseRef);
            throw invalid(name + " is longer than " + MAX_TEXT_LENGTH + " characters");
        }
    }

    private static ServiceException invalid(String message) {
        return new ServiceException(ServiceException.VALIDATION, message);
    }
}
