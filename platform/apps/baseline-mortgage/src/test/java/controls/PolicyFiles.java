package controls;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Reads the bank-owned policy files for mortgage. The directory comes from the system
 * property named by {@link #DIRECTORY_PROPERTY}, or is found by walking up from the
 * working directory. Uses its own small JSON reader so that results do not depend on
 * application code.
 */
final class PolicyFiles {

    static final String DIRECTORY_PROPERTY = "mortgage.controls.dir";

    private PolicyFiles() {
    }

    static Map<String, Object> params() {
        return read("policy-params.json");
    }

    static Map<String, Object> accessPolicy() {
        return read("access-policy.json");
    }

    static Map<String, Object> registry() {
        return read("control-registry.json");
    }

    static Path directory() {
        String configured = System.getProperty(DIRECTORY_PROPERTY);
        if (configured != null && !configured.isBlank()) {
            return Path.of(configured);
        }
        Path current = Path.of("").toAbsolutePath();
        while (current != null) {
            Path candidate = current.resolve("controls").resolve("mortgage");
            if (Files.isRegularFile(candidate.resolve("policy-params.json"))) {
                return candidate;
            }
            current = current.getParent();
        }
        throw new IllegalStateException("controls/mortgage not found; set -D" + DIRECTORY_PROPERTY);
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> read(String name) {
        Path file = directory().resolve(name);
        try {
            String text = Files.readString(file, StandardCharsets.UTF_8);
            return (Map<String, Object>) new Reader(text).document();
        } catch (IOException e) {
            throw new UncheckedIOException("Cannot read " + file, e);
        }
    }

    static BigDecimal decimal(Map<String, Object> object, String key) {
        return (BigDecimal) required(object, key);
    }

    static int integer(Map<String, Object> object, String key) {
        return decimal(object, key).intValueExact();
    }

    @SuppressWarnings("unchecked")
    static List<String> strings(Map<String, Object> object, String key) {
        List<String> values = new ArrayList<>();
        for (Object value : (List<Object>) required(object, key)) {
            values.add((String) value);
        }
        return values;
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> object(Map<String, Object> object, String key) {
        return (Map<String, Object>) required(object, key);
    }

    private static Object required(Map<String, Object> object, String key) {
        Object value = object.get(key);
        if (value == null) {
            throw new IllegalStateException("Policy file has no value for " + key);
        }
        return value;
    }

    /** Strict reader for the subset of JSON the policy files use. */
    private static final class Reader {

        private final String text;
        private int position;

        Reader(String text) {
            this.text = text;
        }

        Object document() {
            Object value = value();
            skipSpace();
            if (position != text.length()) {
                throw new IllegalStateException("Trailing content in policy file at " + position);
            }
            return value;
        }

        private Object value() {
            skipSpace();
            char c = text.charAt(position);
            if (c == '{') {
                return object();
            }
            if (c == '[') {
                return array();
            }
            if (c == '"') {
                return string();
            }
            if (text.startsWith("true", position)) {
                position += 4;
                return Boolean.TRUE;
            }
            if (text.startsWith("false", position)) {
                position += 5;
                return Boolean.FALSE;
            }
            return number();
        }

        private Map<String, Object> object() {
            Map<String, Object> object = new LinkedHashMap<>();
            position++;
            skipSpace();
            if (text.charAt(position) == '}') {
                position++;
                return object;
            }
            while (true) {
                skipSpace();
                String key = string();
                skipSpace();
                expect(':');
                object.put(key, value());
                skipSpace();
                if (text.charAt(position) == '}') {
                    position++;
                    return object;
                }
                expect(',');
            }
        }

        private List<Object> array() {
            List<Object> array = new ArrayList<>();
            position++;
            skipSpace();
            if (text.charAt(position) == ']') {
                position++;
                return array;
            }
            while (true) {
                array.add(value());
                skipSpace();
                if (text.charAt(position) == ']') {
                    position++;
                    return array;
                }
                expect(',');
            }
        }

        private String string() {
            expect('"');
            int end = text.indexOf('"', position);
            String value = text.substring(position, end);
            if (value.indexOf('\\') >= 0) {
                throw new IllegalStateException("Escapes are not used in policy files");
            }
            position = end + 1;
            return value;
        }

        private BigDecimal number() {
            int start = position;
            while (position < text.length() && "-0123456789.".indexOf(text.charAt(position)) >= 0) {
                position++;
            }
            return new BigDecimal(text.substring(start, position));
        }

        private void expect(char expected) {
            if (text.charAt(position) != expected) {
                throw new IllegalStateException("Expected '" + expected + "' at " + position);
            }
            position++;
        }

        private void skipSpace() {
            while (position < text.length() && Character.isWhitespace(text.charAt(position))) {
                position++;
            }
        }
    }
}
