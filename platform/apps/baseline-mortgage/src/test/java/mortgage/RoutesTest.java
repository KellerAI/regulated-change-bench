package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.Test;

class RoutesTest {

    @Test
    void matchesTemplatesAndExtractsParameters() {
        Optional<Routes.Match> match = Routes.find("POST", "/cases/HW-000042/documents/photo_id");
        assertTrue(match.isPresent());
        assertEquals("HW-000042", match.get().params().get("id"));
        assertEquals("photo_id", match.get().params().get("document"));
        assertEquals(Action.EDIT_CASE, match.get().route().action());
    }

    @Test
    void distinguishesMethodsOnTheSamePath() {
        assertEquals(Action.VIEW_CASE, Routes.find("GET", "/cases").orElseThrow().route().action());
        assertEquals(Action.CREATE_CASE, Routes.find("POST", "/cases").orElseThrow().route().action());
        assertFalse(Routes.find("DELETE", "/cases").isPresent());
        assertTrue(Routes.pathExists("/cases"));
    }

    @Test
    void unknownPathsDoNotMatch() {
        assertFalse(Routes.find("GET", "/cases/HW-1/unknown").isPresent());
        assertFalse(Routes.find("GET", "/cases/").isPresent());
        assertFalse(Routes.pathExists("/nowhere"));
    }

    @Test
    void routeKeysAreUnique() {
        Set<String> keys = new HashSet<>();
        for (Route route : Routes.ALL) {
            assertTrue(keys.add(route.key()), route.key());
        }
    }

    @Test
    void healthIsOpen() {
        Route health = Routes.find("GET", "/health").orElseThrow().route();
        assertTrue(health.isOpen());
        assertNull(health.action());
    }
}
