package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.EnumSet;
import org.junit.jupiter.api.Test;

class DocumentChecklistTest {

    @Test
    void employedApplicantsDoNotNeedTaxReturns() {
        LoanCase loanCase = newCase("false");
        assertFalse(DocumentChecklist.required(loanCase).contains(DocumentType.TAX_RETURNS));
        assertEquals(4, DocumentChecklist.missing(loanCase).size());
    }

    @Test
    void selfEmployedApplicantsDo() {
        assertTrue(DocumentChecklist.required(newCase("true")).contains(DocumentType.TAX_RETURNS));
    }

    @Test
    void completeOnceEveryRequiredDocumentIsIn() {
        LoanCase loanCase = newCase("false");
        for (DocumentType document : DocumentChecklist.required(loanCase)) {
            loanCase.markReceived(document);
        }
        assertTrue(DocumentChecklist.isComplete(loanCase));
        DocumentChecklist.Status status = DocumentChecklist.status(loanCase);
        assertEquals(EnumSet.noneOf(DocumentType.class), status.missing());
        assertEquals(status.required(), status.received());
    }

    private static LoanCase newCase(String selfEmployed) {
        LoanCase loanCase = new LoanCase("HW-000040", null, "proc-ada", Fixtures.START);
        loanCase.putApplicantField("self_employed", selfEmployed);
        return loanCase;
    }
}
