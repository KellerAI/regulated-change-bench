package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class JsonTest {

    @Test
    void roundTripsNestedValues() {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("name", "Lena");
        value.put("amount", new BigDecimal("250000.50"));
        value.put("flags", List.of(true, false));
        value.put("missing", null);
        value.put("nested", Map.of("k", "v"));
        assertEquals(value, Json.parse(Json.write(value)));
    }

    @Test
    void escapesSpecialCharacters() {
        String text = "quote \" backslash \\ newline \n tab \t bell \u0007";
        String written = Json.write(text);
        assertTrue(written.contains("\\u0007"));
        assertEquals(text, Json.parse(written));
    }

    @Test
    void readsNumbersAsDecimals() {
        assertEquals(new BigDecimal("1e3"), Json.parse("1e3"));
        assertEquals(new BigDecimal("-12.75"), Json.parse(" -12.75 "));
    }

    @Test
    void emptyBodyIsAnEmptyObject() {
        assertTrue(Json.parseObject("").isEmpty());
        assertTrue(Json.parseObject(null).isEmpty());
    }

    @Test
    void rejectsMalformedInput() {
        assertThrows(IllegalArgumentException.class, () -> Json.parse("{\"a\":1} extra"));
        assertThrows(IllegalArgumentException.class, () -> Json.parse("{\"a\" 1}"));
        assertThrows(IllegalArgumentException.class, () -> Json.parseObject("[1]"));
        assertThrows(IllegalArgumentException.class, () -> Json.parse("\"unterminated"));
    }
}
