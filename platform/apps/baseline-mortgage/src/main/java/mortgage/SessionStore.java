package mortgage;

import java.security.SecureRandom;
import java.time.Clock;
import java.util.Base64;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

/** Issued sessions by bearer token. */
public final class SessionStore {

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int TOKEN_BYTES = 24;

    private final Map<String, Session> sessions = new ConcurrentHashMap<>();
    private final Clock clock;
    private final Supplier<String> tokens;

    public SessionStore(Clock clock) {
        this(clock, SessionStore::randomToken);
    }

    public SessionStore(Clock clock, Supplier<String> tokens) {
        this.clock = clock;
        this.tokens = tokens;
    }

    public Session open(String userId, Role role, boolean mfaVerified) {
        Session session = new Session(tokens.get(), userId, role, mfaVerified, clock);
        sessions.put(session.token(), session);
        return session;
    }

    public Optional<Session> find(String token) {
        if (token == null) {
            return Optional.empty();
        }
        return Optional.ofNullable(sessions.get(token));
    }

    public void close(String token) {
        sessions.remove(token);
    }

    private static String randomToken() {
        byte[] bytes = new byte[TOKEN_BYTES];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }
}
