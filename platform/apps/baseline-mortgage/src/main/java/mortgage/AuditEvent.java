package mortgage;

import java.time.Instant;

/** One entry in the audit trail, linked to its predecessor by hash. */
public record AuditEvent(
        long sequence,
        String actor,
        Action action,
        String target,
        String detail,
        Instant timestamp,
        String previousHash,
        String hash) {
}
