package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ExportTest {

    @Test
    void masksNpiForCallersWithoutNpiAccess() {
        Map<String, String> row = Export.rows(Fixtures.ADMIN, List.of(sampleCase())).get(0);
        assertEquals("*******3456", row.get("ssn"));
        assertEquals("****", row.get("annual_income"));
        assertEquals("Lena Marsh", row.get("full_name"));
        assertEquals("275000", row.get("loan_amount"));
    }

    @Test
    void showsNpiToCallersWhoMayViewIt() {
        Map<String, String> row = Export.rows(Fixtures.PROCESSOR, List.of(sampleCase())).get(0);
        assertEquals("900-12-3456", row.get("ssn"));
    }

    @Test
    void writesCsvWithQuoting() {
        LoanCase loanCase = sampleCase();
        loanCase.putApplicantField("full_name", "Marsh, Lena");
        String csv = Export.toCsv(Export.rows(Fixtures.ADMIN, List.of(loanCase)));
        assertTrue(csv.startsWith("case_id,status,loan_amount,full_name,"));
        assertTrue(csv.contains("\"Marsh, Lena\""));
        assertFalse(csv.contains("900-12-3456"));
        assertEquals("", Export.toCsv(List.of()));
    }

    private static LoanCase sampleCase() {
        LoanCase loanCase = new LoanCase("HW-000030", null, "proc-ada", Fixtures.START);
        for (Map.Entry<String, String> field : Fixtures.applicant("900-12-3456").entrySet()) {
            loanCase.putApplicantField(field.getKey(), field.getValue());
        }
        loanCase.setLoanAmount(new BigDecimal("275000"));
        return loanCase;
    }
}
