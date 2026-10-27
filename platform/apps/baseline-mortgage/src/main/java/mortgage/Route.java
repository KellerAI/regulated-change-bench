package mortgage;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

/**
 * One HTTP route. {@code action} is what the caller is doing; {@code mfaRequired} means the
 * session must have completed step-up MFA. Open routes have no action and need no session.
 */
public record Route(String method, String pattern, Action action, boolean mfaRequired) {

    public static Route open(String method, String pattern) {
        return new Route(method, pattern, null, false);
    }

    public boolean isOpen() {
        return action == null;
    }

    public String key() {
        return method + " " + pattern;
    }

    /** Returns the path parameters when {@code path} fits this route's pattern. */
    public Optional<Map<String, String>> matchPath(String path) {
        String[] expected = segments(pattern);
        String[] actual = segments(path);
        if (expected.length != actual.length) {
            return Optional.empty();
        }
        Map<String, String> params = new HashMap<>();
        for (int i = 0; i < expected.length; i++) {
            if (!matchSegment(expected[i], actual[i], params)) {
                return Optional.empty();
            }
        }
        return Optional.of(params);
    }

    private static boolean matchSegment(String expected, String actual, Map<String, String> params) {
        if (expected.startsWith("{") && expected.endsWith("}")) {
            params.put(expected.substring(1, expected.length() - 1), actual);
            return !actual.isEmpty();
        }
        return expected.equals(actual);
    }

    private static String[] segments(String path) {
        String trimmed = path.startsWith("/") ? path.substring(1) : path;
        return trimmed.split("/", -1);
    }
}
