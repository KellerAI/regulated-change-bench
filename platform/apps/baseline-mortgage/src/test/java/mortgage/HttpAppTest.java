package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class HttpAppTest {

    private static final String NEW_CASE = "{\"applicant\":{\"full_name\":\"Lena Marsh\",\"ssn\":\"900-30-0001\","
            + "\"date_of_birth\":\"1988-02-29\",\"bank_account_number\":\"000123456789\",\"annual_income\":120000},"
            + "\"loan_amount\":\"200000\",\"appraised_value\":\"400000\",\"monthly_debt\":\"500\"}";

    private final Fixtures fixtures = new Fixtures();
    private final AtomicInteger tokens = new AtomicInteger();
    private final SessionStore sessions = new SessionStore(fixtures.clock, () -> "token-" + tokens.incrementAndGet());
    private final HttpApp app = new HttpApp(sessions, fixtures.service, new UserDirectory(fixtures.audit), fixtures.log);

    @Test
    void healthNeedsNoSession() {
        HttpApp.Response response = app.handle(HttpApp.Request.of("GET", "/health", null, null));
        assertEquals(200, response.status());
        assertEquals("{\"status\":\"ok\"}", response.body());
    }

    @Test
    void otherRoutesNeedASession() {
        assertEquals(401, call("GET", "/cases", "missing-token", null).status());
        assertEquals(401, app.handle(HttpApp.Request.of("GET", "/cases", null, null)).status());
    }

    @Test
    void privilegedRoutesNeedStepUpMfa() {
        Session withoutMfa = sessions.open(Fixtures.ADMIN.userId(), Role.ADMIN, false);
        HttpApp.Response response = call("GET", "/exports/cases", withoutMfa.token(), null);
        assertEquals(403, response.status());
        assertTrue(response.body().contains("mfa_required"));
        assertEquals(200, call("GET", "/cases", withoutMfa.token(), null).status());
    }

    @Test
    void idleSessionsLosePrivilegedAccessFirst() {
        Session session = sessions.open(Fixtures.ADMIN.userId(), Role.ADMIN, true);
        fixtures.clock.advance(Duration.ofMinutes(Policy.PRIVILEGED_IDLE_MINUTES + 1));
        HttpApp.Response response = call("GET", "/exports/cases", session.token(), null);
        assertEquals(401, response.status());
        assertTrue(response.body().contains("session_expired"));
        assertEquals(200, call("GET", "/cases", session.token(), null).status());
    }

    @Test
    void createsAndProgressesACaseOverHttp() {
        String processor = sessions.open(Fixtures.PROCESSOR.userId(), Role.PROCESSOR, true).token();
        String underwriter = sessions.open(Fixtures.UNDERWRITER.userId(), Role.UNDERWRITER, true).token();
        HttpApp.Response created = call("POST", "/cases", processor, NEW_CASE);
        assertEquals(200, created.status(), created.body());
        assertFalse(created.body().contains("900-30-0001"));
        String id = (String) Json.parseObject(created.body()).get("id");
        for (String document : new String[] {"photo_id", "pay_stubs", "bank_statements", "appraisal_report"}) {
            assertEquals(200, call("POST", "/cases/" + id + "/documents/" + document, processor, null).status());
        }
        assertEquals(200, call("POST", "/cases/" + id + "/quote", processor, "{\"term_years\":30}").status());
        assertEquals(200, call("POST", "/cases/" + id + "/notes", processor, "{\"text\":\"File complete\"}").status());
        assertEquals(200, call("POST", "/cases/" + id + "/submit", processor, null).status());
        HttpApp.Response approved = call("POST", "/cases/" + id + "/approve", underwriter, null);
        assertEquals("APPROVED", Json.parseObject(approved.body()).get("status"));
        HttpApp.Response npi = call("GET", "/cases/" + id + "/npi", underwriter, null);
        assertEquals("900-30-0001", Json.parseObject(npi.body()).get("ssn"));
    }

    @Test
    void serviceErrorsBecomeStatusCodes() {
        String auditor = sessions.open(Fixtures.AUDITOR.userId(), Role.AUDITOR, true).token();
        String processor = sessions.open(Fixtures.PROCESSOR.userId(), Role.PROCESSOR, true).token();
        assertEquals(403, call("POST", "/cases", auditor, NEW_CASE).status());
        assertEquals(404, call("GET", "/cases/HW-999999", processor, null).status());
        assertEquals(400, call("POST", "/cases", processor, "{\"applicant\":{\"ssn\":\"123\"}}").status());
        assertEquals(400, call("POST", "/cases", processor, "{not json").status());
        assertEquals(400, call("POST", "/cases/HW-000001/documents/passport", processor, null).status());
    }

    @Test
    void unknownRoutesAndMethods() {
        String processor = sessions.open(Fixtures.PROCESSOR.userId(), Role.PROCESSOR, true).token();
        assertEquals(404, call("GET", "/nowhere", processor, null).status());
        assertEquals(405, call("DELETE", "/cases", processor, null).status());
    }

    @Test
    void adminsAssignRolesAndReadTheAuditTrail() {
        String admin = sessions.open(Fixtures.ADMIN.userId(), Role.ADMIN, true).token();
        HttpApp.Response assigned = call("POST", "/admin/users", admin, "{\"user_id\":\"uw-new\",\"role\":\"UNDERWRITER\"}");
        assertEquals(200, assigned.status(), assigned.body());
        HttpApp.Response trail = call("GET", "/audit?target=uw-new", admin, null);
        assertTrue(trail.body().contains("role_assigned:UNDERWRITER"));
        assertEquals(200, call("GET", "/reports/pipeline", admin, null).status());
        assertEquals(200, call("POST", "/admin/retention/purge", admin, null).status());
    }

    @Test
    void servesRequestsOverASocket() throws IOException {
        HttpServer server = app.start(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
        try {
            URL url = new URL("http://127.0.0.1:" + server.getAddress().getPort() + "/health");
            HttpURLConnection connection = (HttpURLConnection) url.openConnection();
            assertEquals(200, connection.getResponseCode());
            try (InputStream body = connection.getInputStream()) {
                assertEquals(Map.of("status", "ok"), Json.parseObject(new String(body.readAllBytes(), StandardCharsets.UTF_8)));
            }
        } finally {
            server.stop(0);
        }
    }

    private HttpApp.Response call(String method, String target, String token, String body) {
        return app.handle(HttpApp.Request.of(method, target, token, body));
    }
}
