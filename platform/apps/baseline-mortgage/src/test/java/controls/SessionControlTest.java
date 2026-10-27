package controls;

import static org.junit.jupiter.api.Assertions.assertTrue;

import mortgage.HttpApp;
import mortgage.Policy;
import mortgage.Role;
import mortgage.Route;
import mortgage.Routes;
import mortgage.Session;
import mortgage.SessionStore;
import mortgage.UserDirectory;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("control")
class SessionControlTest {

    private static final int MINUTES_PER_DAY = 24 * 60;

    @Test
    @Control(obligation = "SES-1", coverage = "exhaustive", domain = "mortgage.privileged_idle_minutes")
    void privilegedIdleTimeoutWithinPolicy() {
        int approvedMinutes = PolicyFiles.integer(PolicyFiles.params(), "mortgage.privileged_idle_minutes");
        Duration approved = Duration.ofMinutes(approvedMinutes);
        assertTrue(Policy.PRIVILEGED_IDLE_MINUTES <= approvedMinutes, "PRIVILEGED_IDLE_MINUTES exceeds the approved " + approvedMinutes);
        assertTrue(
                Session.idleLimit(true).compareTo(approved) <= 0,
                "privileged idle limit exceeds the approved " + approvedMinutes + " minutes");
        List<String> violations = new ArrayList<>();
        checkSessionSweep(approved, violations);
        checkPrivilegedRoutes(approved, violations);
        assertTrue(violations.isEmpty(), "privileged sessions outlive the approved idle limit: " + violations);
    }

    /** Every idle time from one second to a day, minute by minute, against a privileged request. */
    private static void checkSessionSweep(Duration approved, List<String> violations) {
        Instant start = ControlFixtures.START;
        ControlClock clock = new ControlClock(start);
        for (int minutes = 0; minutes <= MINUTES_PER_DAY; minutes++) {
            clock.set(start);
            Session session = new Session("idle-probe", "idle-probe", Role.SENIOR_UNDERWRITER, true, clock);
            Duration idle = Duration.ofMinutes(minutes).plusSeconds(1);
            clock.set(start.plus(idle));
            if (idle.compareTo(approved) > 0 && !session.isIdleExpired(true)) {
                violations.add("session idle " + idle + " still valid");
            }
        }
    }

    /** Each privileged route refuses a session idle one second past the approved limit. */
    private static void checkPrivilegedRoutes(Duration approved, List<String> violations) {
        Set<String> approvedPrivileged = Set.copyOf(PolicyFiles.strings(PolicyFiles.accessPolicy(), "privileged_actions"));
        ControlFixtures fixtures = new ControlFixtures();
        AtomicInteger tokens = new AtomicInteger();
        SessionStore sessions = new SessionStore(fixtures.clock, () -> "idle-probe-" + tokens.incrementAndGet());
        HttpApp app = new HttpApp(sessions, fixtures.service, new UserDirectory(fixtures.audit), fixtures.log);
        for (Route route : Routes.ALL) {
            if (route.isOpen() || !ControlFixtures.isPrivileged(route.action(), approvedPrivileged)) {
                continue;
            }
            fixtures.clock.set(ControlFixtures.START);
            Session session = sessions.open("idle-probe", ControlFixtures.roleHolding(route.action()), true);
            fixtures.clock.set(ControlFixtures.START.plus(approved).plusSeconds(1));
            String path = ControlFixtures.concretePath(route.pattern());
            HttpApp.Response response = app.handle(HttpApp.Request.of(route.method(), path, session.token(), "{}"));
            if (!response.body().contains("\"session_expired\"")) {
                violations.add(route.key() + " served an idle session with " + response.status());
            }
        }
    }
}
