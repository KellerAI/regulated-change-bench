package mortgage;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

/** A clock for tests that only moves when told to. */
final class TestClock extends Clock {

    private Instant now;

    TestClock(Instant start) {
        this.now = start;
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
