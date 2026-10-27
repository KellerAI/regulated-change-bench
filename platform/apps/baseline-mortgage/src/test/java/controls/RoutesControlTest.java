package controls;

import static org.junit.jupiter.api.Assertions.assertTrue;

import mortgage.HttpApp;
import mortgage.Route;
import mortgage.Routes;
import mortgage.Session;
import mortgage.SessionStore;
import mortgage.UserDirectory;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("control")
class RoutesControlTest {

    @Test
    @Control(obligation = "MFA-1", coverage = "exhaustive", domain = "mortgage.routes")
    void privilegedRoutesRequireMfa() {
        Set<String> approvedPrivileged = Set.copyOf(PolicyFiles.strings(PolicyFiles.accessPolicy(), "privileged_actions"));
        ControlFixtures fixtures = new ControlFixtures();
        AtomicInteger tokens = new AtomicInteger();
        SessionStore sessions = new SessionStore(fixtures.clock, () -> "mfa-probe-" + tokens.incrementAndGet());
        HttpApp app = new HttpApp(sessions, fixtures.service, new UserDirectory(fixtures.audit), fixtures.log);
        List<String> violations = new ArrayList<>();
        int privilegedRoutes = 0;
        for (Route route : Routes.ALL) {
            if (route.isOpen() || !ControlFixtures.isPrivileged(route.action(), approvedPrivileged)) {
                continue;
            }
            privilegedRoutes++;
            if (!route.mfaRequired()) {
                violations.add(route.key() + " does not require MFA");
                continue;
            }
            Session withoutMfa = sessions.open("mfa-probe", ControlFixtures.roleHolding(route.action()), false);
            String path = ControlFixtures.concretePath(route.pattern());
            HttpApp.Response response = app.handle(HttpApp.Request.of(route.method(), path, withoutMfa.token(), "{}"));
            if (!response.body().contains("\"mfa_required\"")) {
                violations.add(route.key() + " answered a session without MFA with " + response.status());
            }
        }
        assertTrue(privilegedRoutes > 0, "route table has no privileged routes");
        assertTrue(violations.isEmpty(), "privileged routes without MFA: " + violations);
    }
}
