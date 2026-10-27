package mortgage;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.file.Path;
import java.time.Clock;
import java.util.Locale;

/**
 * Starts the origination API on the loopback interface with synthetic staff accounts.
 * Usage: {@code Main [port] [case-file]}.
 */
public final class Main {

    private static final int DEFAULT_PORT = 8080;

    private Main() {
    }

    public static void main(String[] args) throws IOException {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : DEFAULT_PORT;
        Clock clock = Clock.systemUTC();
        AppLog log = new AppLog(clock, System.err);
        AuditLog audit = new AuditLog(clock);
        CaseStore store = openStore(args);
        CaseService cases = new CaseService(store, audit, log, clock);
        UserDirectory users = new UserDirectory(audit);
        SessionStore sessions = new SessionStore(clock);
        HttpApp app = new HttpApp(sessions, cases, users, log);
        printDemoSessions(users, sessions);
        app.start(new InetSocketAddress(InetAddress.getLoopbackAddress(), port));
        log.info("Fernbrook origination API listening on 127.0.0.1:" + port);
    }

    private static CaseStore openStore(String[] args) {
        if (args.length > 1) {
            return CaseStore.atPath(Path.of(args[1]), new NpiVault());
        }
        return CaseStore.inMemory(new NpiVault());
    }

    /** Synthetic accounts for local use; staff sessions are opened with MFA already completed. */
    private static void printDemoSessions(UserDirectory users, SessionStore sessions) {
        for (Role role : Role.values()) {
            String userId = "demo-" + role.name().toLowerCase(Locale.ROOT).replace('_', '-');
            users.bootstrap(userId, role);
            Session session = sessions.open(userId, role, role != Role.APPLICANT);
            System.out.println(role + " " + userId + " token " + session.token());
        }
    }
}
