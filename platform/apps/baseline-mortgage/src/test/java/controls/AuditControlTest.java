package controls;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import mortgage.Action;
import mortgage.Actor;
import mortgage.AuditEvent;
import mortgage.AuditLog;
import mortgage.LoanCase;
import mortgage.Policy;
import mortgage.Role;
import java.lang.reflect.Method;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("control")
class AuditControlTest {

    private static final Instant GENERATION_START = Instant.parse("2014-01-15T10:00:00Z");
    private static final int GENERATED_MONTHS = 144;
    private static final List<String> MUTATOR_PREFIXES =
            List.of("remove", "delete", "update", "set", "clear", "replace", "edit", "truncate");

    @Test
    @Control(obligation = "AUD-1", coverage = "sample", domain = "mortgage.sampled_operations")
    void sampledOperationsAreAudited() {
        ControlFixtures fixtures = new ControlFixtures();
        Actor processor = ControlFixtures.actor("aud-processor", Role.PROCESSOR);
        Actor underwriter = ControlFixtures.actor("aud-underwriter", Role.UNDERWRITER);
        List<String> missing = new ArrayList<>();

        LoanCase created = fixtures.service.create(
                processor,
                ControlFixtures.applicant("Marlo Penfold", "900-63-1205", "1985-11-02", "006312050044", "118000"),
                ControlFixtures.loan("240000", "360000", "400"));
        expectEvent(fixtures, processor, Action.CREATE_CASE, created.id(), missing);

        fixtures.prepare(processor, created.id());
        fixtures.clock.advance(Duration.ofMinutes(7));
        fixtures.service.submit(processor, created.id());
        expectEvent(fixtures, processor, Action.SUBMIT_CASE, created.id(), missing);

        fixtures.clock.advance(Duration.ofMinutes(11));
        fixtures.service.approve(underwriter, created.id());
        expectEvent(fixtures, underwriter, Action.APPROVE_CREDIT, created.id(), missing);

        assertTrue(missing.isEmpty(), "operations without an audit event: " + missing);
    }

    @Test
    @Control(obligation = "AUD-2", coverage = "exhaustive", domain = "mortgage.audit_retention_and_chain")
    void chainAndRetention() {
        int approvedYears = PolicyFiles.integer(PolicyFiles.params(), "mortgage.audit_retention_years");
        assertTrue(Policy.AUDIT_RETENTION_YEARS >= approvedYears, "AUDIT_RETENTION_YEARS is below the approved " + approvedYears);

        ControlClock clock = new ControlClock(GENERATION_START);
        AuditLog log = generatedLog(clock);
        List<AuditEvent> events = log.events();
        List<String> violations = new ArrayList<>();
        if (!log.verifyChain()) {
            violations.add("a freshly written chain does not verify");
        }
        checkAppendOnly(log, violations);
        checkTamperDetection(clock, log.anchorHash(), events, violations);

        Instant cutoff = ZonedDateTime.ofInstant(clock.instant(), ZoneOffset.UTC).minusYears(approvedYears).toInstant();
        log.purgeOlderThan(clock);
        Set<Long> kept = new HashSet<>();
        for (AuditEvent event : log.events()) {
            kept.add(event.sequence());
        }
        for (AuditEvent event : events) {
            if (!event.timestamp().isBefore(cutoff) && !kept.contains(event.sequence())) {
                violations.add("event " + event.sequence() + " from " + event.timestamp() + " purged inside the retention period");
            }
        }
        if (!log.verifyChain()) {
            violations.add("the retained chain does not verify after a purge");
        }
        assertTrue(violations.isEmpty(), "audit trail problems: " + violations);
    }

    private static void expectEvent(ControlFixtures fixtures, Actor actor, Action action, String target, List<String> missing) {
        Instant now = fixtures.clock.instant();
        for (AuditEvent event : fixtures.audit.events()) {
            boolean sameActor = actor.userId().equals(event.actor());
            boolean sameTarget = target.equals(event.target());
            if (sameActor && event.action() == action && sameTarget && now.equals(event.timestamp())) {
                return;
            }
        }
        missing.add(action + " on " + target + " by " + actor.userId());
    }

    private static AuditLog generatedLog(ControlClock clock) {
        AuditLog log = new AuditLog(clock);
        Actor actor = ControlFixtures.actor("aud-generator", Role.PROCESSOR);
        Action[] actions = Action.values();
        for (int month = 0; month < GENERATED_MONTHS; month++) {
            clock.set(ZonedDateTime.ofInstant(GENERATION_START, ZoneOffset.UTC).plusMonths(month).toInstant());
            log.record(actor, actions[month % actions.length], "HW-" + (100000 + month), "generated");
        }
        return log;
    }

    private static void checkAppendOnly(AuditLog log, List<String> violations) {
        assertThrows(UnsupportedOperationException.class, () -> log.events().clear());
        for (Method method : AuditLog.class.getMethods()) {
            for (String prefix : MUTATOR_PREFIXES) {
                if (method.getName().startsWith(prefix)) {
                    violations.add("AuditLog exposes " + method.getName());
                }
            }
        }
    }

    /** Altering any event, or removing any event that has a successor (with or without relinking), must break the chain. */
    private static void checkTamperDetection(ControlClock clock, String anchor, List<AuditEvent> events, List<String> violations) {
        for (int i = 0; i < events.size(); i++) {
            List<AuditEvent> altered = new ArrayList<>(events);
            altered.set(i, copy(events.get(i), "someone-else", events.get(i).previousHash()));
            if (AuditLog.restore(clock, anchor, altered).verifyChain()) {
                violations.add("altering event " + i + " is not detected");
            }
            if (i < events.size() - 1) {
                List<AuditEvent> shortened = new ArrayList<>(events);
                AuditEvent removed = shortened.remove(i);
                if (AuditLog.restore(clock, anchor, shortened).verifyChain()) {
                    violations.add("removing event " + i + " is not detected");
                }
                AuditEvent successor = shortened.get(i);
                shortened.set(i, copy(successor, successor.actor(), removed.previousHash()));
                if (AuditLog.restore(clock, anchor, shortened).verifyChain()) {
                    violations.add("removing event " + i + " and relinking its successor is not detected");
                }
            }
        }
    }

    private static AuditEvent copy(AuditEvent event, String actor, String previousHash) {
        return new AuditEvent(
                event.sequence(),
                actor,
                event.action(),
                event.target(),
                event.detail(),
                event.timestamp(),
                previousHash,
                event.hash());
    }
}
