package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CaseStoreTest {

    private static final Instant AT = Fixtures.START;

    @Test
    void roundTripsEveryCaseField(@TempDir Path directory) {
        Path file = directory.resolve("cases.json");
        CaseStore.atPath(file, new NpiVault()).save(fullCase());

        LoanCase loaded = CaseStore.atPath(file, new NpiVault()).find("HW-000007").orElseThrow();
        assertEquals("app-lena", loaded.ownerId());
        assertEquals(CaseStatus.REFERRED, loaded.status());
        assertEquals("proc-ada", loaded.preparedBy());
        assertEquals("900-12-3456", loaded.applicantField("ssn"));
        assertEquals("Lena Marsh", loaded.applicantField("full_name"));
        assertEquals(new BigDecimal("350000"), loaded.loanAmount());
        assertEquals(30, loaded.quote().termYears());
        assertEquals(new BigDecimal("2155.01"), loaded.quote().monthlyPayment());
        assertEquals(Decision.Outcome.REFER, loaded.decision().outcome());
        assertEquals(List.of("DTI_ABOVE_POLICY"), loaded.decision().reasons());
        assertEquals(List.of("suw-dev"), loaded.approvers());
        assertEquals("Strong reserves", loaded.overrideReason());
        assertTrue(loaded.isLegalHold());
        assertEquals("Called applicant", loaded.notes().get(0).text());
        assertTrue(loaded.receivedDocuments().contains(DocumentType.PHOTO_ID));
    }

    @Test
    @SuppressWarnings("unchecked")
    void sealsNpiAndKeepsOtherFieldsReadable(@TempDir Path directory) throws IOException {
        Path file = directory.resolve("cases.json");
        CaseStore store = CaseStore.atPath(file, new NpiVault());
        store.save(fullCase());

        Map<String, Object> applicant = (Map<String, Object>) store.atRest("HW-000007").get("applicant");
        assertTrue(NpiVault.isSealed((String) applicant.get("ssn")));
        assertTrue(NpiVault.isSealed((String) applicant.get("annual_income")));
        assertEquals("Lena Marsh", applicant.get("full_name"));
        String text = Files.readString(file);
        assertFalse(text.contains("900-12-3456"));
        assertTrue(text.contains("Lena Marsh"));
    }

    @Test
    void inMemoryStoreListsAndFinds() {
        CaseStore store = CaseStore.inMemory(new NpiVault());
        store.save(fullCase());
        assertEquals(1, store.all().size());
        assertTrue(store.find("HW-000999").isEmpty());
        assertNull(store.atRest("HW-000999"));
    }

    @Test
    void savingAgainReplacesTheCase() {
        CaseStore store = CaseStore.inMemory(new NpiVault());
        LoanCase loanCase = fullCase();
        store.save(loanCase);
        loanCase.moveTo(CaseStatus.APPROVED, AT.plusSeconds(60));
        store.save(loanCase);
        assertEquals(CaseStatus.APPROVED, store.find("HW-000007").orElseThrow().status());
        assertEquals(1, store.all().size());
    }

    private static LoanCase fullCase() {
        LoanCase loanCase = new LoanCase("HW-000007", "app-lena", "app-lena", AT);
        for (Map.Entry<String, String> field : Fixtures.applicant("900-12-3456").entrySet()) {
            loanCase.putApplicantField(field.getKey(), field.getValue());
        }
        loanCase.setLoanAmount(new BigDecimal("350000"));
        loanCase.setAppraisedValue(new BigDecimal("420000"));
        loanCase.setMonthlyDebt(new BigDecimal("2900"));
        loanCase.setQuote(new RateQuote(new BigDecimal("6.250"), 30, new BigDecimal("2155.01"), AT));
        BigDecimal dti = new BigDecimal("50.5501");
        BigDecimal ltv = new BigDecimal("83.3333");
        loanCase.setDecision(new Decision(Decision.Outcome.REFER, dti, ltv, List.of("DTI_ABOVE_POLICY")));
        loanCase.setPreparedBy("proc-ada");
        loanCase.moveTo(CaseStatus.REFERRED, AT);
        loanCase.addApprover("suw-dev");
        loanCase.recordOverride("suw-dev", "Strong reserves");
        loanCase.setLegalHold(true);
        loanCase.addNote(new CaseNote("proc-ada", "Called applicant", AT));
        loanCase.markReceived(DocumentType.PHOTO_ID);
        return loanCase;
    }
}
