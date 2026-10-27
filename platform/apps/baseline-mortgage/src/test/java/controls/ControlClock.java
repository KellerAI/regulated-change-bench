package controls;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

/** A clock that only moves when told to. */
final class ControlClock extends Clock {

    private Instant now;

    ControlClock(Instant start) {
        this.now = start;
    }

    void set(Instant instant) {
        now = instant;
    }

    void advance(Duration duration) {
        now = now.plus(duration);
    }

    void advanceMonths(int months) {
        now = ZonedDateTime.ofInstant(now, ZoneOffset.UTC).plusMonths(months).toInstant();
    }

    @Override
    public ZoneId getZone() {
        return ZoneOffset.UTC;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return this;
    }

    @Override
    public Instant instant() {
        return now;
    }
}
