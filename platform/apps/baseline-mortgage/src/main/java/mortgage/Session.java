package mortgage;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

/** An authenticated session. Idle time is measured with the injected clock. */
public final class Session {

    private final String token;
    private final String userId;
    private final Role role;
    private final boolean mfaVerified;
    private final Clock clock;
    private Instant lastActivity;

    public Session(String token, String userId, Role role, boolean mfaVerified, Clock clock) {
        this.token = token;
        this.userId = userId;
        this.role = role;
        this.mfaVerified = mfaVerified;
        this.clock = clock;
        this.lastActivity = clock.instant();
    }

    /** How long a session may sit idle before it can no longer be used for the given kind of request. */
    public static Duration idleLimit(boolean privileged) {
        if (privileged) {
            return Duration.ofMinutes(Policy.PRIVILEGED_IDLE_MINUTES);
        }
        return Duration.ofMinutes(Policy.STANDARD_IDLE_MINUTES);
    }

    public boolean isIdleExpired(boolean privileged) {
        Duration idle = Duration.between(lastActivity, clock.instant());
        return idle.compareTo(idleLimit(privileged)) > 0;
    }

    public void touch() {
        lastActivity = clock.instant();
    }

    public String token() {
        return token;
    }

    public boolean mfaVerified() {
        return mfaVerified;
    }

    public Instant lastActivity() {
        return lastActivity;
    }

    public Actor actor() {
        return new Actor(userId, role);
    }
}
