package mortgage;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;

/**
 * Append-only audit trail. Each event carries the SHA-256 hash of its predecessor, so
 * any edit, reordering or removal inside the retained window breaks {@link #verifyChain()}.
 */
public final class AuditLog {

    public static final String GENESIS_HASH = "0".repeat(64);

    private final Clock clock;
    private final List<AuditEvent> events = new ArrayList<>();
    private String anchorHash = GENESIS_HASH;
    private long nextSequence = 1;

    public AuditLog(Clock clock) {
        this.clock = clock;
    }

    /** Rebuilds a log from stored events. Callers should verify the chain before trusting it. */
    public static AuditLog restore(Clock clock, String anchorHash, List<AuditEvent> stored) {
        AuditLog log = new AuditLog(clock);
        log.anchorHash = anchorHash;
        log.events.addAll(stored);
        if (!stored.isEmpty()) {
            log.nextSequence = stored.get(stored.size() - 1).sequence() + 1;
        }
        return log;
    }

    public synchronized AuditEvent record(Actor actor, Action action, String target, String detail) {
        long sequence = nextSequence;
        nextSequence++;
        Instant now = clock.instant();
        String previous = lastHash();
        String hash = hashOf(sequence, actor.userId(), action, target, detail, now, previous);
        AuditEvent event = new AuditEvent(sequence, actor.userId(), action, target, detail, now, previous, hash);
        events.add(event);
        return event;
    }

    public synchronized List<AuditEvent> events() {
        return List.copyOf(events);
    }

    public synchronized List<AuditEvent> eventsFor(String target) {
        List<AuditEvent> matching = new ArrayList<>();
        for (AuditEvent event : events) {
            if (event.target().equals(target)) {
                matching.add(event);
            }
        }
        return matching;
    }

    public synchronized String anchorHash() {
        return anchorHash;
    }

    public synchronized boolean verifyChain() {
        String expectedPrevious = anchorHash;
        for (AuditEvent event : events) {
            if (!event.previousHash().equals(expectedPrevious)) {
                return false;
            }
            if (!rehash(event).equals(event.hash())) {
                return false;
            }
            expectedPrevious = event.hash();
        }
        return true;
    }

    /**
     * Drops events older than the audit retention period. The hash of the last dropped
     * event becomes the anchor, so the retained chain still verifies.
     */
    public synchronized int purgeOlderThan(Clock now) {
        Instant cutoff = retentionCutoff(now);
        int removed = 0;
        while (!events.isEmpty() && events.get(0).timestamp().isBefore(cutoff)) {
            anchorHash = events.remove(0).hash();
            removed++;
        }
        return removed;
    }

    public static Instant retentionCutoff(Clock now) {
        ZonedDateTime current = ZonedDateTime.ofInstant(now.instant(), ZoneOffset.UTC);
        return current.minusYears(Policy.AUDIT_RETENTION_YEARS).toInstant();
    }

    public static String hashOf(
            long sequence,
            String actor,
            Action action,
            String target,
            String detail,
            Instant timestamp,
            String previousHash) {
        String material = sequence + "|" + actor + "|" + action + "|" + target + "|" + detail + "|" + timestamp + "|" + previousHash;
        return sha256(material);
    }

    private String lastHash() {
        if (events.isEmpty()) {
            return anchorHash;
        }
        return events.get(events.size() - 1).hash();
    }

    private static String rehash(AuditEvent event) {
        return hashOf(
                event.sequence(),
                event.actor(),
                event.action(),
                event.target(),
                event.detail(),
                event.timestamp(),
                event.previousHash());
    }

    private static String sha256(String material) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(material.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is not available", e);
        }
    }
}
