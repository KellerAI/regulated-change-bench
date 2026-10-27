package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.function.Executable;
import org.junit.jupiter.api.io.TempDir;

class CaseServiceTest {

    private final Fixtures fixtures = new Fixtures();
    private final CaseService service = fixtures.service;

    @Test
    void createStartsADraftAndAuditsIt() {
        LoanCase created = fixtures.draft(Fixtures.PROCESSOR, "900-10-0001", Fixtures.eligibleLoan());
        assertEquals("HW-000001", created.id());
        assertEquals(CaseStatus.DRAFT, created.status());
        assertNull(created.ownerId());
        AuditEvent event = fixtures.audit.eventsFor(created.id()).get(0);
        assertEquals(Action.CREATE_CASE, event.action());
        assertEquals(Fixtures.PROCESSOR.userId(), event.actor());
    }

    @Test
    void applicantsOnlySeeTheirOwnCases() {
        LoanCase mine = fixtures.draft(Fixtures.APPLICANT, "900-10-0002", Fixtures.eligibleLoan());
        fixtures.draft(Fixtures.PROCESSOR, "900-10-0003", Fixtures.eligibleLoan());
        assertEquals(Fixtures.APPLICANT.userId(), mine.ownerId());
        assertEquals(List.of(mine.id()), ids(service.list(Fixtures.APPLICANT)));
        assertEquals(2, service.list(Fixtures.PROCESSOR).size());
        expectCode(ServiceException.NOT_FOUND, () -> service.view(Fixtures.OTHER_APPLICANT, mine.id()));
    }

    @Test
    void createNeedsLoanTerms() {
        expectCode(ServiceException.VALIDATION, () -> service.create(Fixtures.PROCESSOR, Fixtures.applicant("900-10-0004"), null));
        LoanRequest zeroLoan = Fixtures.loan("0", "400000", "0");
        expectCode(ServiceException.VALIDATION, () -> service.create(Fixtures.PROCESSOR, Fixtures.applicant("900-10-0004"), zeroLoan));
    }

    @Test
    void duplicateApplicationsAreRejected() {
        fixtures.draft(Fixtures.PROCESSOR, "900-10-0005", Fixtures.eligibleLoan());
        expectCode(ServiceException.DUPLICATE, () -> fixtures.draft(Fixtures.APPLICANT, "900-10-0005", Fixtures.eligibleLoan()));
    }

    @Test
    void withdrawnApplicationsDoNotBlockANewOne() {
        LoanCase first = fixtures.draft(Fixtures.PROCESSOR, "900-10-0006", Fixtures.eligibleLoan());
        service.withdraw(Fixtures.PROCESSOR, first.id());
        assertNotNull(fixtures.draft(Fixtures.PROCESSOR, "900-10-0006", Fixtures.eligibleLoan()));
    }

    @Test
    void editingLoanTermsDropsTheQuote() {
        LoanCase ready = fixtures.ready(Fixtures.PROCESSOR, "900-10-0007", Fixtures.eligibleLoan());
        assertNotNull(ready.quote());
        LoanRequest larger = Fixtures.loan("210000", "400000", "500");
        LoanCase edited = service.edit(Fixtures.PROCESSOR, ready.id(), Map.of("employer", "Harbour Freight Co"), larger);
        assertNull(edited.quote());
        assertEquals("Harbour Freight Co", edited.applicantField("employer"));
    }

    @Test
    void submissionNeedsDocumentsAndAQuote() {
        LoanCase draft = fixtures.draft(Fixtures.PROCESSOR, "900-10-0008", Fixtures.eligibleLoan());
        expectCode(ServiceException.VALIDATION, () -> service.submit(Fixtures.PROCESSOR, draft.id()));
        for (DocumentType document : DocumentChecklist.required(draft)) {
            service.markDocumentReceived(Fixtures.PROCESSOR, draft.id(), document);
        }
        expectCode(ServiceException.VALIDATION, () -> service.submit(Fixtures.PROCESSOR, draft.id()));
        service.quote(Fixtures.PROCESSOR, draft.id(), 30);
        assertEquals(CaseStatus.SUBMITTED, service.submit(Fixtures.PROCESSOR, draft.id()).status());
    }

    @Test
    void submissionNeedsTheRequiredApplicantFields() {
        LoanCase ready = fixtures.ready(Fixtures.PROCESSOR, "900-10-0009", Fixtures.eligibleLoan());
        Map<String, String> clearDateOfBirth = new HashMap<>();
        clearDateOfBirth.put("date_of_birth", null);
        service.edit(Fixtures.PROCESSOR, ready.id(), clearDateOfBirth, null);
        expectCode(ServiceException.VALIDATION, () -> service.submit(Fixtures.PROCESSOR, ready.id()));
    }

    @Test
    void eligibleCasesAreApprovedByAnUnderwriter() {
        LoanCase submitted = fixtures.submitted("900-10-0010", Fixtures.eligibleLoan());
        assertEquals(Decision.Outcome.AUTO_APPROVE_ELIGIBLE, submitted.decision().outcome());
        assertEquals(Fixtures.PROCESSOR.userId(), submitted.preparedBy());
        LoanCase approved = service.approve(Fixtures.UNDERWRITER, submitted.id());
        assertEquals(CaseStatus.APPROVED, approved.status());
        assertEquals(List.of(Fixtures.UNDERWRITER.userId()), approved.approvers());
    }

    @Test
    void referredCasesNeedASeniorOverride() {
        LoanCase referred = fixtures.submitted("900-10-0011", Fixtures.referredLoan());
        assertEquals(CaseStatus.REFERRED, referred.status());
        expectCode(ServiceException.INVALID_STATE, () -> service.approve(Fixtures.UNDERWRITER, referred.id()));
        expectCode(ServiceException.FORBIDDEN, () -> service.override(Fixtures.UNDERWRITER, referred.id(), "Reserves"));
        LoanCase approved = service.override(Fixtures.SENIOR, referred.id(), "Twelve months of reserves");
        assertEquals(CaseStatus.APPROVED, approved.status());
        assertEquals(Fixtures.SENIOR.userId(), approved.overrideBy());
    }

    @Test
    void overridesNeedAJustification() {
        LoanCase referred = fixtures.submitted("900-10-0012", Fixtures.referredLoan());
        expectCode(ServiceException.VALIDATION, () -> service.override(Fixtures.SENIOR, referred.id(), " "));
    }

    @Test
    void largeOverridesWaitForASecondSenior() {
        Map<String, String> applicant = Fixtures.applicant("900-10-0013");
        applicant.put("annual_income", "300000");
        LoanCase referred = fixtures.submitted(applicant, Fixtures.loan("1600000", "2000000", "1500"));
        LoanCase afterOverride = service.override(Fixtures.SENIOR, referred.id(), "Strong guarantor");
        assertEquals(CaseStatus.REFERRED, afterOverride.status());
        LoanCase approved = service.approve(Fixtures.SECOND_SENIOR, referred.id());
        assertEquals(CaseStatus.APPROVED, approved.status());
    }

    @Test
    void hardStopsAreDeclinedNotOverridden() {
        LoanCase referred = fixtures.submitted("900-10-0014", Fixtures.loan("450000", "400000", "500"));
        assertEquals(Decision.Outcome.DECLINE, referred.decision().outcome());
        expectCode(ServiceException.INVALID_STATE, () -> service.override(Fixtures.SENIOR, referred.id(), "Exception"));
        LoanCase declined = service.decline(Fixtures.UNDERWRITER, referred.id(), "Loan exceeds value");
        assertEquals(CaseStatus.DECLINED, declined.status());
        assertEquals(List.of("LTV_HARD_STOP", "Loan exceeds value"), declined.declineReasons());
    }

    @Test
    void draftsCannotBeDeclined() {
        LoanCase draft = fixtures.draft(Fixtures.PROCESSOR, "900-10-0015", Fixtures.eligibleLoan());
        expectCode(ServiceException.INVALID_STATE, () -> service.decline(Fixtures.UNDERWRITER, draft.id(), null));
    }

    @Test
    void approvedCasesCloseAndApplicantsCanWithdraw() {
        LoanCase submitted = fixtures.submitted("900-10-0016", Fixtures.eligibleLoan());
        service.approve(Fixtures.UNDERWRITER, submitted.id());
        assertEquals(CaseStatus.CLOSED, service.close(Fixtures.PROCESSOR, submitted.id()).status());
        expectCode(ServiceException.INVALID_STATE, () -> service.withdraw(Fixtures.PROCESSOR, submitted.id()));

        LoanCase own = fixtures.ready(Fixtures.APPLICANT, "900-10-0017", Fixtures.eligibleLoan());
        service.submit(Fixtures.APPLICANT, own.id());
        expectCode(ServiceException.FORBIDDEN, () -> service.addNote(Fixtures.APPLICANT, own.id(), "Any news?"));
        assertEquals(CaseStatus.WITHDRAWN, service.withdraw(Fixtures.APPLICANT, own.id()).status());
    }

    @Test
    void notesAreKeptInOrderAndAudited() {
        LoanCase draft = fixtures.draft(Fixtures.PROCESSOR, "900-10-0018", Fixtures.eligibleLoan());
        service.addNote(Fixtures.PROCESSOR, draft.id(), "Left voicemail");
        fixtures.clock.advance(Duration.ofHours(2));
        service.addNote(Fixtures.UNDERWRITER, draft.id(), "Need second pay stub");
        List<CaseNote> notes = service.notes(Fixtures.AUDITOR, draft.id());
        assertEquals(List.of("Left voicemail", "Need second pay stub"), notes.stream().map(CaseNote::text).toList());
        assertEquals(Fixtures.UNDERWRITER.userId(), notes.get(1).author());
        expectCode(ServiceException.VALIDATION, () -> service.addNote(Fixtures.PROCESSOR, draft.id(), ""));
        expectCode(ServiceException.FORBIDDEN, () -> service.addNote(Fixtures.AUDITOR, draft.id(), "Looks fine"));
    }

    @Test
    void checklistShowsWhatIsMissing() {
        LoanCase draft = fixtures.draft(Fixtures.PROCESSOR, "900-10-0019", Fixtures.eligibleLoan());
        service.markDocumentReceived(Fixtures.PROCESSOR, draft.id(), DocumentType.PHOTO_ID);
        DocumentChecklist.Status status = service.checklist(Fixtures.PROCESSOR, draft.id());
        assertTrue(status.received().contains(DocumentType.PHOTO_ID));
        assertFalse(status.missing().contains(DocumentType.PHOTO_ID));
        assertEquals(3, status.missing().size());
    }

    @Test
    void npiViewsAreAuditedAndRestricted() {
        LoanCase draft = fixtures.draft(Fixtures.PROCESSOR, "900-10-0020", Fixtures.eligibleLoan());
        Map<String, String> npi = service.viewNpi(Fixtures.UNDERWRITER, draft.id());
        assertEquals("900-10-0020", npi.get("ssn"));
        assertEquals(List.of("annual_income", "bank_account_number", "date_of_birth", "ssn"), List.copyOf(npi.keySet()));
        assertEquals(Action.VIEW_NPI, last(fixtures.audit.events()).action());
        expectCode(ServiceException.FORBIDDEN, () -> service.viewNpi(Fixtures.ADMIN, draft.id()));
    }

    @Test
    void retentionPurgeSkipsCasesOnLegalHold() {
        LoanCase first = fixtures.submitted("900-10-0021", Fixtures.referredLoan());
        LoanCase second = fixtures.submitted("900-10-0022", Fixtures.referredLoan());
        service.decline(Fixtures.UNDERWRITER, first.id(), null);
        service.decline(Fixtures.UNDERWRITER, second.id(), null);
        service.setLegalHold(Fixtures.ADMIN, second.id(), true);
        fixtures.clock.advanceMonths(Policy.DECLINED_NPI_RETENTION_MONTHS + 1);
        assertEquals(List.of(first.id()), service.purgeExpiredNpi(Fixtures.ADMIN));
        assertNull(fixtures.store.find(first.id()).orElseThrow().applicantField("ssn"));
        assertNotNull(fixtures.store.find(second.id()).orElseThrow().applicantField("ssn"));
        expectCode(ServiceException.FORBIDDEN, () -> service.purgeExpiredNpi(Fixtures.SENIOR));
    }

    @Test
    void exportsAreMaskedAndAudited() {
        fixtures.draft(Fixtures.PROCESSOR, "900-10-0023", Fixtures.eligibleLoan());
        List<Map<String, String>> rows = service.export(Fixtures.ADMIN);
        assertEquals("*******0023", rows.get(0).get("ssn"));
        assertEquals(Action.EXPORT_CASES, last(fixtures.audit.events()).action());
        expectCode(ServiceException.FORBIDDEN, () -> service.export(Fixtures.PROCESSOR));
    }

    @Test
    void auditorsReadTheTrail() {
        LoanCase draft = fixtures.draft(Fixtures.PROCESSOR, "900-10-0024", Fixtures.eligibleLoan());
        assertEquals(1, service.auditTrail(Fixtures.AUDITOR, draft.id()).size());
        assertEquals(1, service.auditTrail(Fixtures.ADMIN, null).size());
        expectCode(ServiceException.FORBIDDEN, () -> service.auditTrail(Fixtures.UNDERWRITER, null));
    }

    @Test
    void pipelineReflectsTheCallersCases() {
        fixtures.draft(Fixtures.APPLICANT, "900-10-0025", Fixtures.eligibleLoan());
        fixtures.submitted("900-10-0026", Fixtures.eligibleLoan());
        assertEquals(1, service.pipeline(Fixtures.APPLICANT).row(CaseStatus.DRAFT).count());
        assertEquals(0, service.pipeline(Fixtures.APPLICANT).row(CaseStatus.SUBMITTED).count());
        PipelineReport staff = service.pipeline(Fixtures.PROCESSOR);
        assertEquals(new BigDecimal("200000"), staff.row(CaseStatus.SUBMITTED).totalLoanAmount());
    }

    @Test
    void caseNumbersContinueAfterARestart(@TempDir Path directory) {
        Path file = directory.resolve("cases.json");
        CaseService first = new CaseService(CaseStore.atPath(file, new NpiVault()), fixtures.audit, fixtures.log, fixtures.clock);
        first.create(Fixtures.PROCESSOR, Fixtures.applicant("900-10-0027"), Fixtures.eligibleLoan());
        CaseService restarted = new CaseService(CaseStore.atPath(file, new NpiVault()), fixtures.audit, fixtures.log, fixtures.clock);
        LoanCase next = restarted.create(Fixtures.PROCESSOR, Fixtures.applicant("900-10-0028"), Fixtures.eligibleLoan());
        assertEquals("HW-000002", next.id());
    }

    private static void expectCode(String code, Executable operation) {
        ServiceException refused = assertThrows(ServiceException.class, operation);
        assertEquals(code, refused.code(), refused.getMessage());
    }

    private static List<String> ids(List<LoanCase> cases) {
        return cases.stream().map(LoanCase::id).toList();
    }

    private static <T> T last(List<T> items) {
        return items.get(items.size() - 1);
    }
}
