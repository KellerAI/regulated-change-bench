package mortgage;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** JSON shapes returned by the HTTP API. Case summaries show NPI masked. */
final class CaseViews {

    private CaseViews() {
    }

    static Map<String, Object> summary(LoanCase loanCase) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("id", loanCase.id());
        view.put("status", loanCase.status().name());
        view.put("status_changed_at", text(loanCase.statusChangedAt()));
        view.put("created_by", loanCase.createdBy());
        view.put("prepared_by", loanCase.preparedBy());
        view.put("applicant", maskedApplicant(loanCase));
        view.put("loan_amount", text(loanCase.loanAmount()));
        view.put("appraised_value", text(loanCase.appraisedValue()));
        view.put("monthly_debt", text(loanCase.monthlyDebt()));
        view.put("quote", quote(loanCase.quote()));
        view.put("decision", decision(loanCase.decision()));
        view.put("approvers", loanCase.approvers());
        view.put("override_by", loanCase.overrideBy());
        view.put("decline_reasons", loanCase.declineReasons());
        view.put("legal_hold", loanCase.isLegalHold());
        view.put("npi_purged_at", text(loanCase.npiPurgedAt()));
        return view;
    }

    static List<Object> summaries(List<LoanCase> cases) {
        List<Object> views = new ArrayList<>();
        for (LoanCase loanCase : cases) {
            views.add(summary(loanCase));
        }
        return views;
    }

    static Map<String, Object> quote(RateQuote quote) {
        if (quote == null) {
            return null;
        }
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("rate_percent", text(quote.ratePercent()));
        view.put("term_years", quote.termYears());
        view.put("monthly_payment", text(quote.monthlyPayment()));
        view.put("quoted_at", text(quote.quotedAt()));
        return view;
    }

    static Map<String, Object> note(CaseNote note) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("author", note.author());
        view.put("text", note.text());
        view.put("created_at", text(note.createdAt()));
        return view;
    }

    static List<Object> notes(List<CaseNote> notes) {
        List<Object> views = new ArrayList<>();
        for (CaseNote note : notes) {
            views.add(note(note));
        }
        return views;
    }

    static Map<String, Object> checklist(DocumentChecklist.Status status) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("required", names(status.required()));
        view.put("received", names(status.received()));
        view.put("missing", names(status.missing()));
        return view;
    }

    static Map<String, Object> pipeline(PipelineReport report) {
        List<Object> rows = new ArrayList<>();
        for (PipelineReport.Row row : report.rows()) {
            Map<String, Object> view = new LinkedHashMap<>();
            view.put("status", row.status().name());
            view.put("count", row.count());
            view.put("total_loan_amount", text(row.totalLoanAmount()));
            rows.add(view);
        }
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("as_of", text(report.asOf()));
        view.put("rows", rows);
        view.put("stale_cases", report.staleCases());
        return view;
    }

    static List<Object> auditEvents(List<AuditEvent> events) {
        List<Object> views = new ArrayList<>();
        for (AuditEvent event : events) {
            Map<String, Object> view = new LinkedHashMap<>();
            view.put("sequence", event.sequence());
            view.put("actor", event.actor());
            view.put("action", event.action().name());
            view.put("target", event.target());
            view.put("detail", event.detail());
            view.put("timestamp", text(event.timestamp()));
            view.put("hash", event.hash());
            views.add(view);
        }
        return views;
    }

    private static Map<String, Object> maskedApplicant(LoanCase loanCase) {
        Map<String, Object> view = new LinkedHashMap<>();
        for (Map.Entry<String, String> field : loanCase.applicant().entrySet()) {
            view.put(field.getKey(), maskIfNpi(field.getKey(), field.getValue()));
        }
        return view;
    }

    private static String maskIfNpi(String field, String value) {
        return NpiRegistry.isNpi(field) ? Mask.npi(value) : value;
    }

    private static Map<String, Object> decision(Decision decision) {
        if (decision == null) {
            return null;
        }
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("outcome", decision.outcome().name());
        view.put("dti_percent", text(decision.dtiPercent()));
        view.put("ltv_percent", text(decision.ltvPercent()));
        view.put("reasons", decision.reasons());
        return view;
    }

    private static List<Object> names(Iterable<? extends Enum<?>> values) {
        List<Object> names = new ArrayList<>();
        for (Enum<?> value : values) {
            names.add(value.name());
        }
        return names;
    }

    private static String text(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof BigDecimal decimal) {
            return decimal.toPlainString();
        }
        if (value instanceof Instant instant) {
            return instant.toString();
        }
        return value.toString();
    }
}
