package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class AuditLogTest {

    private final TestClock clock = new TestClock(Fixtures.START);
    private final AuditLog log = new AuditLog(clock);

    @Test
    void eventsAreChainedFromGenesis() {
        AuditEvent first = log.record(Fixtures.PROCESSOR, Action.CREATE_CASE, "HW-000001", "created");
        AuditEvent second = log.record(Fixtures.PROCESSOR, Action.SUBMIT_CASE, "HW-000001", "REFER");
        assertEquals(AuditLog.GENESIS_HASH, first.previousHash());
        assertEquals(first.hash(), second.previousHash());
        assertEquals(2, second.sequence());
        assertTrue(log.verifyChain());
    }

    @Test
    void recordsWhoDidWhatToWhatAndWhen() {
        AuditEvent event = log.record(Fixtures.UNDERWRITER, Action.APPROVE_CREDIT, "HW-000003", "approved");
        assertEquals("uw-ben", event.actor());
        assertEquals(Action.APPROVE_CREDIT, event.action());
        assertEquals("HW-000003", event.target());
        assertEquals(Fixtures.START, event.timestamp());
    }

    @Test
    void editedEventsBreakTheChain() {
        log.record(Fixtures.PROCESSOR, Action.CREATE_CASE, "HW-000001", "created");
        log.record(Fixtures.PROCESSOR, Action.EDIT_CASE, "HW-000001", "edited");
        List<AuditEvent> events = new ArrayList<>(log.events());
        AuditEvent original = events.get(0);
        events.set(0, new AuditEvent(original.sequence(), original.actor(), Action.PURGE_NPI, original.target(),
                original.detail(), original.timestamp(), original.previousHash(), original.hash()));
        assertFalse(AuditLog.restore(clock, log.anchorHash(), events).verifyChain());
    }

    @Test
    void restoredLogsContinueTheSequence() {
        log.record(Fixtures.PROCESSOR, Action.CREATE_CASE, "HW-000001", "created");
        AuditLog restored = AuditLog.restore(clock, log.anchorHash(), log.events());
        AuditEvent next = restored.record(Fixtures.PROCESSOR, Action.EDIT_CASE, "HW-000001", "edited");
        assertEquals(2, next.sequence());
        assertTrue(restored.verifyChain());
    }

    @Test
    void purgeKeepsTheRetentionWindowAndAnchorsTheChain() {
        log.record(Fixtures.ADMIN, Action.MANAGE_USERS, "uw-ben", "role_assigned:UNDERWRITER");
        clock.advance(Duration.ofDays(365L * 8));
        AuditEvent recent = log.record(Fixtures.ADMIN, Action.MANAGE_USERS, "uw-cora", "role_assigned:UNDERWRITER");
        assertEquals(1, log.purgeOlderThan(clock));
        assertEquals(List.of(recent), log.events());
        assertTrue(log.verifyChain());
    }

    @Test
    void filtersByTarget() {
        log.record(Fixtures.PROCESSOR, Action.CREATE_CASE, "HW-000001", "created");
        log.record(Fixtures.PROCESSOR, Action.CREATE_CASE, "HW-000002", "created");
        assertEquals(1, log.eventsFor("HW-000002").size());
    }
}
