package mortgage;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** A mortgage application and its origination state. Applicant fields are held in clear in memory. */
public final class LoanCase {

    private final String id;
    private final String ownerId;
    private final String createdBy;
    private final Instant createdAt;
    private final Map<String, String> applicant = new LinkedHashMap<>();
    private final List<String> approvers = new ArrayList<>();
    private final List<String> declineReasons = new ArrayList<>();
    private final List<CaseNote> notes = new ArrayList<>();
    private final Set<DocumentType> receivedDocuments = EnumSet.noneOf(DocumentType.class);
    private CaseStatus status = CaseStatus.DRAFT;
    private Instant statusChangedAt;
    private String preparedBy;
    private BigDecimal loanAmount = BigDecimal.ZERO;
    private BigDecimal appraisedValue = BigDecimal.ZERO;
    private BigDecimal monthlyDebt = BigDecimal.ZERO;
    private RateQuote quote;
    private Decision decision;
    private String overrideBy;
    private String overrideReason;
    private boolean legalHold;
    private Instant npiPurgedAt;

    public LoanCase(String id, String ownerId, String createdBy, Instant createdAt) {
        this.id = id;
        this.ownerId = ownerId;
        this.createdBy = createdBy;
        this.createdAt = createdAt;
        this.statusChangedAt = createdAt;
    }

    public String id() {
        return id;
    }

    /** The applicant's portal user, or null for cases keyed in by staff. */
    public String ownerId() {
        return ownerId;
    }

    public String createdBy() {
        return createdBy;
    }

    public Instant createdAt() {
        return createdAt;
    }

    public CaseStatus status() {
        return status;
    }

    public Instant statusChangedAt() {
        return statusChangedAt;
    }

    public void moveTo(CaseStatus next, Instant at) {
        status = next;
        statusChangedAt = at;
    }

    /** The user who submitted the case for a decision. */
    public String preparedBy() {
        return preparedBy;
    }

    public void setPreparedBy(String userId) {
        preparedBy = userId;
    }

    public Map<String, String> applicant() {
        return Collections.unmodifiableMap(applicant);
    }

    public String applicantField(String name) {
        return applicant.get(name);
    }

    public void putApplicantField(String name, String value) {
        if (value == null) {
            applicant.remove(name);
        } else {
            applicant.put(name, value);
        }
    }

    public void removeApplicantField(String name) {
        applicant.remove(name);
    }

    public BigDecimal loanAmount() {
        return loanAmount;
    }

    public void setLoanAmount(BigDecimal amount) {
        loanAmount = amount;
    }

    public BigDecimal appraisedValue() {
        return appraisedValue;
    }

    public void setAppraisedValue(BigDecimal value) {
        appraisedValue = value;
    }

    public BigDecimal monthlyDebt() {
        return monthlyDebt;
    }

    public void setMonthlyDebt(BigDecimal debt) {
        monthlyDebt = debt;
    }

    public RateQuote quote() {
        return quote;
    }

    public void setQuote(RateQuote rateQuote) {
        quote = rateQuote;
    }

    public Decision decision() {
        return decision;
    }

    public void setDecision(Decision underwritingDecision) {
        decision = underwritingDecision;
    }

    public List<String> approvers() {
        return Collections.unmodifiableList(approvers);
    }

    public void addApprover(String userId) {
        approvers.add(userId);
    }

    public String overrideBy() {
        return overrideBy;
    }

    public String overrideReason() {
        return overrideReason;
    }

    public void recordOverride(String userId, String reason) {
        overrideBy = userId;
        overrideReason = reason;
    }

    public List<String> declineReasons() {
        return Collections.unmodifiableList(declineReasons);
    }

    public void setDeclineReasons(List<String> reasons) {
        declineReasons.clear();
        declineReasons.addAll(reasons);
    }

    public boolean isLegalHold() {
        return legalHold;
    }

    public void setLegalHold(boolean hold) {
        legalHold = hold;
    }

    public Instant npiPurgedAt() {
        return npiPurgedAt;
    }

    public void markNpiPurged(Instant at) {
        npiPurgedAt = at;
    }

    public List<CaseNote> notes() {
        return Collections.unmodifiableList(notes);
    }

    public void addNote(CaseNote note) {
        notes.add(note);
    }

    public Set<DocumentType> receivedDocuments() {
        return Collections.unmodifiableSet(receivedDocuments);
    }

    public void markReceived(DocumentType document) {
        receivedDocuments.add(document);
    }

    public Application toApplication() {
        BigDecimal payment = quote == null ? null : quote.monthlyPayment();
        return new Application(loanAmount, appraisedValue, annualIncome(), monthlyDebt, payment);
    }

    private BigDecimal annualIncome() {
        String income = applicant.get("annual_income");
        if (income == null) {
            return null;
        }
        return new BigDecimal(income);
    }
}
