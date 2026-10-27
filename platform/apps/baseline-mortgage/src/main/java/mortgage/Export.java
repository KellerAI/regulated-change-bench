package mortgage;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Case export for reporting teams. NPI is masked unless the caller may view it. */
public final class Export {

    private static final List<String> APPLICANT_COLUMNS = List.of(
            "full_name",
            "email",
            "ssn",
            "date_of_birth",
            "bank_account_number",
            "annual_income");

    private Export() {
    }

    public static List<Map<String, String>> rows(Actor caller, List<LoanCase> cases) {
        boolean revealNpi = AccessMatrix.isAllowed(caller.role(), Action.VIEW_NPI);
        List<Map<String, String>> rows = new ArrayList<>();
        for (LoanCase loanCase : cases) {
            rows.add(row(loanCase, revealNpi));
        }
        return rows;
    }

    public static String toCsv(List<Map<String, String>> rows) {
        StringBuilder csv = new StringBuilder();
        if (rows.isEmpty()) {
            return csv.toString();
        }
        csv.append(String.join(",", rows.get(0).keySet())).append('\n');
        for (Map<String, String> row : rows) {
            csv.append(csvLine(row)).append('\n');
        }
        return csv.toString();
    }

    private static Map<String, String> row(LoanCase loanCase, boolean revealNpi) {
        Map<String, String> row = new LinkedHashMap<>();
        row.put("case_id", loanCase.id());
        row.put("status", loanCase.status().name());
        row.put("loan_amount", plain(loanCase.loanAmount()));
        for (String column : APPLICANT_COLUMNS) {
            row.put(column, exportValue(column, loanCase.applicantField(column), revealNpi));
        }
        return row;
    }

    private static String exportValue(String field, String value, boolean revealNpi) {
        if (value == null) {
            return "";
        }
        if (NpiRegistry.isNpi(field) && !revealNpi) {
            return Mask.npi(value);
        }
        return value;
    }

    private static String csvLine(Map<String, String> row) {
        List<String> cells = new ArrayList<>();
        for (String value : row.values()) {
            cells.add(csvCell(value));
        }
        return String.join(",", cells);
    }

    private static String csvCell(String value) {
        if (value.contains(",") || value.contains("\"") || value.contains("\n")) {
            return "\"" + value.replace("\"", "\"\"") + "\"";
        }
        return value;
    }

    private static String plain(BigDecimal amount) {
        return amount == null ? "" : amount.toPlainString();
    }
}
