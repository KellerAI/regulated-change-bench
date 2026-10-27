package mortgage;

import java.math.BigDecimal;
import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Case operations. Every operation checks the caller against {@link AccessMatrix} and every
 * state-changing operation writes an audit event. Log lines never carry raw NPI.
 */
public final class CaseService {

    private static final String ID_PREFIX = "HW-";

    private final CaseStore store;
    private final AuditLog audit;
    private final AppLog log;
    private final Clock clock;
    private final Underwriting underwriting = new Underwriting();
    private final Retention retention;
    private final ApplicantValidator validator;
    private final AtomicLong sequence;

    public CaseService(CaseStore store, AuditLog audit, AppLog log, Clock clock) {
        this.store = store;
        this.audit = audit;
        this.log = log;
        this.clock = clock;
        this.retention = new Retention(clock);
        this.validator = new ApplicantValidator(log);
        this.sequence = new AtomicLong(highestSequence(store));
    }

    public LoanCase create(Actor actor, Map<String, String> applicant, LoanRequest loan) {
        authorize(actor, Action.CREATE_CASE);
        validator.validate("new case", applicant);
        requireLoanTerms(loan);
        rejectDuplicate(applicant.get("ssn"));
        LoanCase loanCase = new LoanCase(nextId(), ownerFor(actor), actor.userId(), clock.instant());
        applyApplicant(loanCase, applicant);
        applyLoan(loanCase, loan);
        store.save(loanCase);
        audit.record(actor, Action.CREATE_CASE, loanCase.id(), "created");
        log.info("Case " + loanCase.id() + " created by " + actor.userId());
        return loanCase;
    }

    public LoanCase edit(Actor actor, String caseId, Map<String, String> applicantChanges, LoanRequest loanChanges) {
        authorize(actor, Action.EDIT_CASE);
        LoanCase loanCase = load(actor, caseId);
        requireStatus(loanCase, CaseStatus.DRAFT);
        validator.validate(caseId, applicantChanges);
        applyApplicant(loanCase, applicantChanges);
        applyLoan(loanCase, loanChanges);
        store.save(loanCase);
        audit.record(actor, Action.EDIT_CASE, caseId, "edited");
        return loanCase;
    }

    public LoanCase view(Actor actor, String caseId) {
        authorize(actor, Action.VIEW_CASE);
        return load(actor, caseId);
    }

    public List<LoanCase> list(Actor actor) {
        authorize(actor, Action.VIEW_CASE);
        return visibleCases(actor);
    }

    public Map<String, String> viewNpi(Actor actor, String caseId) {
        authorize(actor, Action.VIEW_NPI);
        LoanCase loanCase = load(actor, caseId);
        Map<String, String> npi = new LinkedHashMap<>();
        for (String field : new TreeSet<>(NpiRegistry.FIELDS)) {
            String value = loanCase.applicantField(field);
            if (value != null) {
                npi.put(field, value);
            }
        }
        audit.record(actor, Action.VIEW_NPI, caseId, "npi_viewed");
        return npi;
    }

    public LoanCase submit(Actor actor, String caseId) {
        authorize(actor, Action.SUBMIT_CASE);
        LoanCase loanCase = load(actor, caseId);
        requireStatus(loanCase, CaseStatus.DRAFT);
        requireReadyToSubmit(loanCase);
        Decision decision = underwriting.decide(loanCase.toApplication());
        loanCase.setDecision(decision);
        loanCase.setPreparedBy(actor.userId());
        loanCase.moveTo(statusFor(decision), clock.instant());
        store.save(loanCase);
        audit.record(actor, Action.SUBMIT_CASE, caseId, decision.outcome().name());
        log.info("Case " + caseId + " submitted by " + actor.userId() + "; underwriting outcome " + decision.outcome());
        return loanCase;
    }

    public LoanCase approve(Actor actor, String caseId) {
        authorize(actor, Action.APPROVE_CREDIT);
        LoanCase loanCase = load(actor, caseId);
        requireApprovable(loanCase);
        boolean complete = recordApproval(loanCase, actor);
        if (complete) {
            loanCase.moveTo(CaseStatus.APPROVED, clock.instant());
        }
        store.save(loanCase);
        audit.record(actor, Action.APPROVE_CREDIT, caseId, complete ? "approved" : "approval_recorded");
        log.info("Case " + caseId + " approval recorded for " + actor.userId() + "; complete=" + complete);
        return loanCase;
    }

    public LoanCase override(Actor actor, String caseId, String justification) {
        authorize(actor, Action.OVERRIDE_POLICY);
        LoanCase loanCase = load(actor, caseId);
        requireStatus(loanCase, CaseStatus.REFERRED);
        requireOverridable(loanCase, justification);
        boolean complete = recordApproval(loanCase, actor);
        loanCase.recordOverride(actor.userId(), justification.strip());
        if (complete) {
            loanCase.moveTo(CaseStatus.APPROVED, clock.instant());
        }
        store.save(loanCase);
        audit.record(actor, Action.OVERRIDE_POLICY, caseId, complete ? "override_approved" : "override_recorded");
        log.info("Case " + caseId + " policy override by " + actor.userId() + "; complete=" + complete);
        return loanCase;
    }

    public LoanCase decline(Actor actor, String caseId, String reason) {
        authorize(actor, Action.DECLINE_CREDIT);
        LoanCase loanCase = load(actor, caseId);
        requireAwaitingDecision(loanCase);
        loanCase.setDeclineReasons(declineReasons(loanCase, reason));
        loanCase.moveTo(CaseStatus.DECLINED, clock.instant());
        store.save(loanCase);
        audit.record(actor, Action.DECLINE_CREDIT, caseId, "declined");
        log.info("Case " + caseId + " declined by " + actor.userId());
        return loanCase;
    }

    public LoanCase withdraw(Actor actor, String caseId) {
        authorize(actor, Action.EDIT_CASE);
        LoanCase loanCase = load(actor, caseId);
        if (!loanCase.status().isActive()) {
            throw invalidState("Case " + caseId + " is no longer active");
        }
        loanCase.moveTo(CaseStatus.WITHDRAWN, clock.instant());
        store.save(loanCase);
        audit.record(actor, Action.EDIT_CASE, caseId, "withdrawn");
        log.info("Case " + caseId + " withdrawn by " + actor.userId());
        return loanCase;
    }

    public LoanCase close(Actor actor, String caseId) {
        authorize(actor, Action.EDIT_CASE);
        LoanCase loanCase = load(actor, caseId);
        requireChangeAllowed(actor, loanCase);
        requireStatus(loanCase, CaseStatus.APPROVED);
        loanCase.moveTo(CaseStatus.CLOSED, clock.instant());
        store.save(loanCase);
        audit.record(actor, Action.EDIT_CASE, caseId, "closed");
        log.info("Case " + caseId + " closed by " + actor.userId());
        return loanCase;
    }

    public CaseNote addNote(Actor actor, String caseId, String text) {
        authorize(actor, Action.EDIT_CASE);
        LoanCase loanCase = load(actor, caseId);
        requireChangeAllowed(actor, loanCase);
        CaseNote note = CaseNote.of(actor.userId(), text, clock.instant());
        loanCase.addNote(note);
        store.save(loanCase);
        audit.record(actor, Action.EDIT_CASE, caseId, "note_added");
        return note;
    }

    public List<CaseNote> notes(Actor actor, String caseId) {
        authorize(actor, Action.VIEW_CASE);
        return load(actor, caseId).notes();
    }

    public DocumentChecklist.Status markDocumentReceived(Actor actor, String caseId, DocumentType document) {
        authorize(actor, Action.EDIT_CASE);
        LoanCase loanCase = load(actor, caseId);
        requireChangeAllowed(actor, loanCase);
        loanCase.markReceived(document);
        store.save(loanCase);
        audit.record(actor, Action.EDIT_CASE, caseId, "document_received:" + document);
        return DocumentChecklist.status(loanCase);
    }

    public DocumentChecklist.Status checklist(Actor actor, String caseId) {
        authorize(actor, Action.VIEW_CASE);
        return DocumentChecklist.status(load(actor, caseId));
    }

    public RateQuote quote(Actor actor, String caseId, int termYears) {
        authorize(actor, Action.EDIT_CASE);
        LoanCase loanCase = load(actor, caseId);
        requireStatus(loanCase, CaseStatus.DRAFT);
        RateQuote quote = RateQuote.price(loanCase.loanAmount(), loanCase.appraisedValue(), termYears, clock.instant());
        loanCase.setQuote(quote);
        store.save(loanCase);
        audit.record(actor, Action.EDIT_CASE, caseId, "quoted:" + termYears + "y");
        return quote;
    }

    public PipelineReport pipeline(Actor actor) {
        authorize(actor, Action.VIEW_CASE);
        return PipelineReport.build(visibleCases(actor), clock.instant());
    }

    public List<Map<String, String>> export(Actor actor) {
        authorize(actor, Action.EXPORT_CASES);
        List<Map<String, String>> rows = Export.rows(actor, store.all());
        audit.record(actor, Action.EXPORT_CASES, "cases", rows.size() + " rows");
        log.info("Exported " + rows.size() + " cases for " + actor.userId());
        return rows;
    }

    public LoanCase setLegalHold(Actor actor, String caseId, boolean hold) {
        authorize(actor, Action.PURGE_NPI);
        LoanCase loanCase = load(actor, caseId);
        loanCase.setLegalHold(hold);
        store.save(loanCase);
        audit.record(actor, Action.PURGE_NPI, caseId, hold ? "legal_hold_placed" : "legal_hold_released");
        log.info("Legal hold on case " + caseId + " set to " + hold + " by " + actor.userId());
        return loanCase;
    }

    public List<String> purgeExpiredNpi(Actor actor) {
        authorize(actor, Action.PURGE_NPI);
        List<String> purged = new ArrayList<>();
        for (LoanCase loanCase : store.all()) {
            if (retention.isPurgeDue(loanCase)) {
                retention.purge(loanCase);
                store.save(loanCase);
                audit.record(actor, Action.PURGE_NPI, loanCase.id(), "npi_purged");
                purged.add(loanCase.id());
            }
        }
        log.info("Retention purge removed NPI from " + purged.size() + " cases");
        return purged;
    }

    public List<AuditEvent> auditTrail(Actor actor, String target) {
        authorize(actor, Action.VIEW_AUDIT);
        if (target == null) {
            return audit.events();
        }
        return audit.eventsFor(target);
    }

    private void authorize(Actor actor, Action action) {
        if (!AccessMatrix.isAllowed(actor.role(), action)) {
            log.warn("Denied " + action + " to " + actor.userId() + " (" + actor.role() + ")");
            throw new ServiceException(ServiceException.FORBIDDEN, "Not permitted: " + action);
        }
    }

    private LoanCase load(Actor actor, String caseId) {
        LoanCase loanCase = store.find(caseId).orElseThrow(() -> notFound(caseId));
        if (!isVisibleTo(actor, loanCase)) {
            throw notFound(caseId);
        }
        return loanCase;
    }

    private List<LoanCase> visibleCases(Actor actor) {
        List<LoanCase> visible = new ArrayList<>();
        for (LoanCase loanCase : store.all()) {
            if (isVisibleTo(actor, loanCase)) {
                visible.add(loanCase);
            }
        }
        return visible;
    }

    private static boolean isVisibleTo(Actor actor, LoanCase loanCase) {
        if (actor.role() != Role.APPLICANT) {
            return true;
        }
        return actor.userId().equals(loanCase.ownerId());
    }

    private static String ownerFor(Actor actor) {
        return actor.role() == Role.APPLICANT ? actor.userId() : null;
    }

    private void rejectDuplicate(String ssn) {
        if (ssn == null) {
            return;
        }
        for (LoanCase existing : store.all()) {
            if (existing.status().isActive() && ssn.equals(existing.applicantField("ssn"))) {
                log.warn("Duplicate application for applicant " + Mask.npi(ssn) + " matches case " + existing.id());
                throw new ServiceException(ServiceException.DUPLICATE, "An active application already exists for this applicant");
            }
        }
    }

    private void requireReadyToSubmit(LoanCase loanCase) {
        List<String> missingFields = missingFields(loanCase);
        if (!missingFields.isEmpty()) {
            log.warn("Submit blocked for case " + loanCase.id() + ": missing fields " + missingFields);
            throw validation("Missing applicant fields: " + missingFields);
        }
        Set<DocumentType> missingDocuments = DocumentChecklist.missing(loanCase);
        if (!missingDocuments.isEmpty()) {
            log.warn("Submit blocked for case " + loanCase.id() + ": missing documents " + missingDocuments);
            throw validation("Missing documents: " + missingDocuments);
        }
        if (loanCase.quote() == null) {
            log.warn("Submit blocked for case " + loanCase.id() + ": no rate quote");
            throw validation("A rate quote is required before submission");
        }
    }

    private static List<String> missingFields(LoanCase loanCase) {
        List<String> missing = new ArrayList<>();
        for (String field : ApplicantFields.REQUIRED_FOR_SUBMIT) {
            if (loanCase.applicantField(field) == null) {
                missing.add(field);
            }
        }
        return missing;
    }

    private static CaseStatus statusFor(Decision decision) {
        if (decision.outcome() == Decision.Outcome.AUTO_APPROVE_ELIGIBLE) {
            return CaseStatus.SUBMITTED;
        }
        return CaseStatus.REFERRED;
    }

    private boolean recordApproval(LoanCase loanCase, Actor actor) {
        try {
            return Approvals.approve(loanCase, actor);
        } catch (ServiceException e) {
            log.warn("Approval by " + actor.userId() + " rejected on case " + loanCase.id() + ": " + e.code());
            throw e;
        }
    }

    private static void requireApprovable(LoanCase loanCase) {
        boolean eligible = loanCase.status() == CaseStatus.SUBMITTED && isAutoApproveEligible(loanCase.decision());
        boolean overridden = loanCase.status() == CaseStatus.REFERRED && loanCase.overrideBy() != null;
        if (!eligible && !overridden) {
            throw invalidState("Case " + loanCase.id() + " is not awaiting approval");
        }
    }

    private static boolean isAutoApproveEligible(Decision decision) {
        return decision != null && decision.outcome() == Decision.Outcome.AUTO_APPROVE_ELIGIBLE;
    }

    private static void requireOverridable(LoanCase loanCase, String justification) {
        if (loanCase.overrideBy() != null) {
            throw invalidState("Case " + loanCase.id() + " already has a policy override");
        }
        if (loanCase.decision() == null || loanCase.decision().outcome() != Decision.Outcome.REFER) {
            throw invalidState("Only referred decisions can be overridden; hard stops must be declined");
        }
        if (justification == null || justification.isBlank()) {
            throw validation("A policy override needs a justification");
        }
    }

    private static void requireAwaitingDecision(LoanCase loanCase) {
        if (!loanCase.status().awaitsDecision()) {
            throw invalidState("Case " + loanCase.id() + " is not awaiting a decision");
        }
    }

    private static List<String> declineReasons(LoanCase loanCase, String reason) {
        List<String> reasons = new ArrayList<>();
        if (loanCase.decision() != null) {
            reasons.addAll(loanCase.decision().reasons());
        }
        if (reason != null && !reason.isBlank()) {
            reasons.add(reason.strip());
        }
        return reasons;
    }

    /** Applicants may only change their own case while it is still a draft (withdrawal aside). */
    private static void requireChangeAllowed(Actor actor, LoanCase loanCase) {
        if (actor.role() == Role.APPLICANT && loanCase.status() != CaseStatus.DRAFT) {
            throw new ServiceException(ServiceException.FORBIDDEN, "Applicants can only change draft cases");
        }
    }

    private static void requireStatus(LoanCase loanCase, CaseStatus expected) {
        if (loanCase.status() != expected) {
            throw invalidState("Case " + loanCase.id() + " is " + loanCase.status() + ", expected " + expected);
        }
    }

    private static void requireLoanTerms(LoanRequest loan) {
        if (loan == null || loan.loanAmount() == null || loan.appraisedValue() == null) {
            throw validation("Loan amount and appraised value are required");
        }
    }

    private static void applyApplicant(LoanCase loanCase, Map<String, String> fields) {
        for (Map.Entry<String, String> field : fields.entrySet()) {
            loanCase.putApplicantField(field.getKey(), field.getValue());
        }
    }

    private static void applyLoan(LoanCase loanCase, LoanRequest loan) {
        if (loan == null) {
            return;
        }
        if (loan.loanAmount() != null) {
            loanCase.setLoanAmount(positive("loan_amount", loan.loanAmount()));
            loanCase.setQuote(null);
        }
        if (loan.appraisedValue() != null) {
            loanCase.setAppraisedValue(positive("appraised_value", loan.appraisedValue()));
            loanCase.setQuote(null);
        }
        if (loan.monthlyDebt() != null) {
            loanCase.setMonthlyDebt(nonNegative("monthly_debt", loan.monthlyDebt()));
        }
    }

    private static BigDecimal positive(String name, BigDecimal value) {
        if (value.signum() <= 0) {
            throw validation(name + " must be greater than zero");
        }
        return value;
    }

    private static BigDecimal nonNegative(String name, BigDecimal value) {
        if (value.signum() < 0) {
            throw validation(name + " cannot be negative");
        }
        return value;
    }

    private String nextId() {
        return String.format("%s%06d", ID_PREFIX, sequence.incrementAndGet());
    }

    private static long highestSequence(CaseStore store) {
        long highest = 0;
        for (LoanCase loanCase : store.all()) {
            long number = Long.parseLong(loanCase.id().substring(ID_PREFIX.length()));
            highest = Math.max(highest, number);
        }
        return highest;
    }

    private static ServiceException notFound(String caseId) {
        return new ServiceException(ServiceException.NOT_FOUND, "No case " + caseId);
    }

    private static ServiceException invalidState(String message) {
        return new ServiceException(ServiceException.INVALID_STATE, message);
    }

    private static ServiceException validation(String message) {
        return new ServiceException(ServiceException.VALIDATION, message);
    }
}
