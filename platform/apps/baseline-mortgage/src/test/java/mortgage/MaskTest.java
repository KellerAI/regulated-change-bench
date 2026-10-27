package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class MaskTest {

    @Test
    void keepsTheLastFourCharactersOfLongValues() {
        assertEquals("*******3456", Mask.npi("900-12-3456"));
        assertEquals("********6789", Mask.npi("000123456789"));
    }

    @Test
    void hidesShortValuesCompletely() {
        assertEquals("****", Mask.npi("120000"));
        assertEquals("****", Mask.npi("42"));
    }

    @Test
    void describesMissingValues() {
        assertEquals("[none]", Mask.npi(null));
    }
}
