package mortgage;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Case persistence. Cases are held as JSON documents, in memory and optionally in a file.
 * Applicant fields listed in {@link NpiRegistry} are sealed with {@link NpiVault} before they
 * are stored; other fields are stored as given.
 */
public final class CaseStore {

    private static final String FORMAT = "mortgage-cases/1";

    private final Map<String, Map<String, Object>> documents = new LinkedHashMap<>();
    private final NpiVault vault;
    private final Path file;

    private CaseStore(NpiVault vault, Path file) {
        this.vault = vault;
        this.file = file;
    }

    public static CaseStore inMemory(NpiVault vault) {
        return new CaseStore(vault, null);
    }

    public static CaseStore atPath(Path file, NpiVault vault) {
        CaseStore store = new CaseStore(vault, file);
        store.load();
        return store;
    }

    public synchronized void save(LoanCase loanCase) {
        documents.put(loanCase.id(), toDocument(loanCase));
        flush();
    }

    public synchronized Optional<LoanCase> find(String id) {
        Map<String, Object> document = documents.get(id);
        if (document == null) {
            return Optional.empty();
        }
        return Optional.of(fromDocument(document));
    }

    public synchronized List<LoanCase> all() {
        List<LoanCase> cases = new ArrayList<>();
        for (Map<String, Object> document : documents.values()) {
            cases.add(fromDocument(document));
        }
        return cases;
    }

    /** A copy of the stored document for a case, exactly as it is held at rest. */
    public synchronized Map<String, Object> atRest(String id) {
        Map<String, Object> document = documents.get(id);
        if (document == null) {
            return null;
        }
        return Json.parseObject(Json.write(document));
    }

    private Map<String, Object> sealApplicant(Map<String, String> applicant) {
        Map<String, Object> stored = new LinkedHashMap<>();
        for (Map.Entry<String, String> field : applicant.entrySet()) {
            stored.put(field.getKey(), protect(field.getKey(), field.getValue()));
        }
        return stored;
    }

    private String protect(String name, String value) {
        if (NpiRegistry.isNpi(name)) {
            return vault.seal(value);
        }
        return value;
    }

    private void openApplicant(LoanCase loanCase, Map<String, Object> stored) {
        for (Map.Entry<String, Object> field : stored.entrySet()) {
            loanCase.putApplicantField(field.getKey(), reveal(field.getKey(), (String) field.getValue()));
        }
    }

    private String reveal(String field, String value) {
        if (NpiVault.isSealed(value)) {
            return vault.open(value);
        }
        return value;
    }

    private Map<String, Object> toDocument(LoanCase loanCase) {
        Map<String, Object> document = new LinkedHashMap<>();
        document.put("id", loanCase.id());
        document.put("owner_id", loanCase.ownerId());
        document.put("created_by", loanCase.createdBy());
        document.put("created_at", text(loanCase.createdAt()));
        document.put("status", loanCase.status().name());
        document.put("status_changed_at", text(loanCase.statusChangedAt()));
        document.put("prepared_by", loanCase.preparedBy());
        document.put("applicant", sealApplicant(loanCase.applicant()));
        document.put("loan_amount", text(loanCase.loanAmount()));
        document.put("appraised_value", text(loanCase.appraisedValue()));
        document.put("monthly_debt", text(loanCase.monthlyDebt()));
        document.put("quote", quoteDocument(loanCase.quote()));
        document.put("decision", decisionDocument(loanCase.decision()));
        document.put("approvers", new ArrayList<>(loanCase.approvers()));
        document.put("override_by", loanCase.overrideBy());
        document.put("override_reason", loanCase.overrideReason());
        document.put("decline_reasons", new ArrayList<>(loanCase.declineReasons()));
        document.put("legal_hold", loanCase.isLegalHold());
        document.put("npi_purged_at", text(loanCase.npiPurgedAt()));
        document.put("notes", notesDocument(loanCase.notes()));
        document.put("received_documents", documentNames(loanCase));
        return document;
    }

    @SuppressWarnings("unchecked")
    private LoanCase fromDocument(Map<String, Object> document) {
        LoanCase loanCase = new LoanCase(
                (String) document.get("id"),
                (String) document.get("owner_id"),
                (String) document.get("created_by"),
                instant(document.get("created_at")));
        loanCase.moveTo(CaseStatus.valueOf((String) document.get("status")), instant(document.get("status_changed_at")));
        loanCase.setPreparedBy((String) document.get("prepared_by"));
        openApplicant(loanCase, (Map<String, Object>) document.get("applicant"));
        loanCase.setLoanAmount(decimal(document.get("loan_amount")));
        loanCase.setAppraisedValue(decimal(document.get("appraised_value")));
        loanCase.setMonthlyDebt(decimal(document.get("monthly_debt")));
        loanCase.setQuote(quoteFrom((Map<String, Object>) document.get("quote")));
        loanCase.setDecision(decisionFrom((Map<String, Object>) document.get("decision")));
        for (Object approver : (List<Object>) document.get("approvers")) {
            loanCase.addApprover((String) approver);
        }
        loanCase.recordOverride((String) document.get("override_by"), (String) document.get("override_reason"));
        loanCase.setDeclineReasons(strings((List<Object>) document.get("decline_reasons")));
        loanCase.setLegalHold(Boolean.TRUE.equals(document.get("legal_hold")));
        loanCase.markNpiPurged(instant(document.get("npi_purged_at")));
        restoreNotes(loanCase, (List<Object>) document.get("notes"));
        for (Object name : (List<Object>) document.get("received_documents")) {
            loanCase.markReceived(DocumentType.valueOf((String) name));
        }
        return loanCase;
    }

    private static Map<String, Object> quoteDocument(RateQuote quote) {
        if (quote == null) {
            return null;
        }
        Map<String, Object> document = new LinkedHashMap<>();
        document.put("rate_percent", text(quote.ratePercent()));
        document.put("term_years", String.valueOf(quote.termYears()));
        document.put("monthly_payment", text(quote.monthlyPayment()));
        document.put("quoted_at", text(quote.quotedAt()));
        return document;
    }

    private static RateQuote quoteFrom(Map<String, Object> document) {
        if (document == null) {
            return null;
        }
        return new RateQuote(
                decimal(document.get("rate_percent")),
                Integer.parseInt((String) document.get("term_years")),
                decimal(document.get("monthly_payment")),
                instant(document.get("quoted_at")));
    }

    private static Map<String, Object> decisionDocument(Decision decision) {
        if (decision == null) {
            return null;
        }
        Map<String, Object> document = new LinkedHashMap<>();
        document.put("outcome", decision.outcome().name());
        document.put("dti_percent", text(decision.dtiPercent()));
        document.put("ltv_percent", text(decision.ltvPercent()));
        document.put("reasons", new ArrayList<>(decision.reasons()));
        return document;
    }

    @SuppressWarnings("unchecked")
    private static Decision decisionFrom(Map<String, Object> document) {
        if (document == null) {
            return null;
        }
        return new Decision(
                Decision.Outcome.valueOf((String) document.get("outcome")),
                decimal(document.get("dti_percent")),
                decimal(document.get("ltv_percent")),
                strings((List<Object>) document.get("reasons")));
    }

    private static List<Object> notesDocument(List<CaseNote> notes) {
        List<Object> documents = new ArrayList<>();
        for (CaseNote note : notes) {
            Map<String, Object> document = new LinkedHashMap<>();
            document.put("author", note.author());
            document.put("text", note.text());
            document.put("created_at", text(note.createdAt()));
            documents.add(document);
        }
        return documents;
    }

    @SuppressWarnings("unchecked")
    private static void restoreNotes(LoanCase loanCase, List<Object> documents) {
        for (Object item : documents) {
            Map<String, Object> document = (Map<String, Object>) item;
            String author = (String) document.get("author");
            String text = (String) document.get("text");
            loanCase.addNote(new CaseNote(author, text, instant(document.get("created_at"))));
        }
    }

    private static List<Object> documentNames(LoanCase loanCase) {
        List<Object> names = new ArrayList<>();
        for (DocumentType document : loanCase.receivedDocuments()) {
            names.add(document.name());
        }
        return names;
    }

    private static List<String> strings(List<Object> values) {
        List<String> strings = new ArrayList<>();
        for (Object value : values) {
            strings.add((String) value);
        }
        return strings;
    }

    private static String text(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof BigDecimal decimal) {
            return decimal.toPlainString();
        }
        return value.toString();
    }

    private static BigDecimal decimal(Object value) {
        return value == null ? null : new BigDecimal((String) value);
    }

    private static Instant instant(Object value) {
        return value == null ? null : Instant.parse((String) value);
    }

    private void flush() {
        if (file == null) {
            return;
        }
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("format", FORMAT);
        root.put("cases", documents);
        try {
            Path temporary = file.resolveSibling(file.getFileName() + ".tmp");
            Files.writeString(temporary, Json.write(root), StandardCharsets.UTF_8);
            Files.move(temporary, file, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) {
            throw new UncheckedIOException("Could not write case file " + file, e);
        }
    }

    @SuppressWarnings("unchecked")
    private void load() {
        if (!Files.exists(file)) {
            return;
        }
        try {
            Map<String, Object> root = Json.parseObject(Files.readString(file, StandardCharsets.UTF_8));
            Map<String, Object> cases = (Map<String, Object>) root.get("cases");
            for (Map.Entry<String, Object> entry : cases.entrySet()) {
                documents.put(entry.getKey(), (Map<String, Object>) entry.getValue());
            }
        } catch (IOException e) {
            throw new UncheckedIOException("Could not read case file " + file, e);
        }
    }
}
