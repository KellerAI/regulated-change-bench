package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class SessionTest {

    private final TestClock clock = new TestClock(Fixtures.START);

    @Test
    void privilegedRequestsUseTheShorterIdleLimit() {
        Session session = new Session("t", "uw-ben", Role.UNDERWRITER, true, clock);
        clock.advance(Duration.ofMinutes(20));
        assertTrue(session.isIdleExpired(true));
        assertFalse(session.isIdleExpired(false));
    }

    @Test
    void sessionsExpireAfterTheStandardLimit() {
        Session session = new Session("t", "proc-ada", Role.PROCESSOR, false, clock);
        clock.advance(Duration.ofMinutes(31));
        assertTrue(session.isIdleExpired(false));
    }

    @Test
    void exactlyAtTheLimitIsStillValid() {
        Session session = new Session("t", "uw-ben", Role.UNDERWRITER, true, clock);
        clock.advance(Session.idleLimit(true));
        assertFalse(session.isIdleExpired(true));
    }

    @Test
    void activityResetsTheIdleTimer() {
        Session session = new Session("t", "uw-ben", Role.UNDERWRITER, true, clock);
        clock.advance(Duration.ofMinutes(10));
        session.touch();
        clock.advance(Duration.ofMinutes(10));
        assertFalse(session.isIdleExpired(true));
    }

    @Test
    void storeIssuesFindsAndClosesSessions() {
        AtomicInteger counter = new AtomicInteger();
        SessionStore store = new SessionStore(clock, () -> "tok-" + counter.incrementAndGet());
        Session session = store.open("suw-dev", Role.SENIOR_UNDERWRITER, true);
        assertEquals("tok-1", session.token());
        assertEquals(new Actor("suw-dev", Role.SENIOR_UNDERWRITER), store.find("tok-1").orElseThrow().actor());
        store.close("tok-1");
        assertTrue(store.find("tok-1").isEmpty());
        assertTrue(store.find(null).isEmpty());
    }

    @Test
    void defaultTokensAreLongAndDistinct() {
        SessionStore store = new SessionStore(clock);
        String first = store.open("a", Role.PROCESSOR, false).token();
        String second = store.open("b", Role.PROCESSOR, false).token();
        assertTrue(first.length() >= 32);
        assertFalse(first.equals(second));
    }
}
