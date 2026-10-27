package mortgage;

import java.util.EnumSet;
import java.util.Set;

/** Which supporting documents a case needs before it can be submitted. */
public final class DocumentChecklist {

    private static final Set<DocumentType> ALWAYS_REQUIRED = EnumSet.of(
            DocumentType.PHOTO_ID,
            DocumentType.PAY_STUBS,
            DocumentType.BANK_STATEMENTS,
            DocumentType.APPRAISAL_REPORT);

    private DocumentChecklist() {
    }

    /** A view of the checklist for display. */
    public record Status(Set<DocumentType> required, Set<DocumentType> received, Set<DocumentType> missing) {
    }

    public static Set<DocumentType> required(LoanCase loanCase) {
        Set<DocumentType> required = EnumSet.copyOf(ALWAYS_REQUIRED);
        // Self-employed income is verified from tax returns rather than pay stubs alone.
        if ("true".equals(loanCase.applicantField("self_employed"))) {
            required.add(DocumentType.TAX_RETURNS);
        }
        return required;
    }

    public static Set<DocumentType> missing(LoanCase loanCase) {
        Set<DocumentType> missing = required(loanCase);
        missing.removeAll(loanCase.receivedDocuments());
        return missing;
    }

    public static boolean isComplete(LoanCase loanCase) {
        return missing(loanCase).isEmpty();
    }

    public static Status status(LoanCase loanCase) {
        return new Status(required(loanCase), loanCase.receivedDocuments(), missing(loanCase));
    }
}
