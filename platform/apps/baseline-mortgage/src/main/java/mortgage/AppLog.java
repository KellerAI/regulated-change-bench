package mortgage;

import java.io.PrintStream;
import java.time.Clock;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;

/**
 * Application log. Keeps the most recent lines in memory and optionally echoes them to a
 * stream. Never pass raw NPI here; use {@link Mask#npi(String)}.
 */
public final class AppLog {

    private static final int MAX_LINES = 10_000;

    private final Clock clock;
    private final PrintStream echo;
    private final Deque<String> lines = new ArrayDeque<>();

    public AppLog(Clock clock) {
        this(clock, null);
    }

    public AppLog(Clock clock, PrintStream echo) {
        this.clock = clock;
        this.echo = echo;
    }

    public void info(String message) {
        write("INFO", message);
    }

    public void warn(String message) {
        write("WARN", message);
    }

    public void error(String message) {
        write("ERROR", message);
    }

    public synchronized List<String> lines() {
        return List.copyOf(lines);
    }

    private synchronized void write(String level, String message) {
        String line = clock.instant() + " " + level + " " + message;
        lines.addLast(line);
        if (lines.size() > MAX_LINES) {
            lines.removeFirst();
        }
        if (echo != null) {
            echo.println(line);
        }
    }
}
