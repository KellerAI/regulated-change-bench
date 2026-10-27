package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Base64;
import org.junit.jupiter.api.Test;

class NpiVaultTest {

    private final NpiVault vault = new NpiVault();

    @Test
    void sealedValuesOpenToTheOriginal() {
        String sealed = vault.seal("900-12-3456");
        assertTrue(NpiVault.isSealed(sealed));
        assertFalse(sealed.contains("3456"));
        assertEquals("900-12-3456", vault.open(sealed));
    }

    @Test
    void sealingTwiceGivesDifferentCiphertexts() {
        assertNotEquals(vault.seal("1975-07-04"), vault.seal("1975-07-04"));
    }

    @Test
    void tamperingIsDetected() {
        String sealed = vault.seal("000123456789");
        String prefix = sealed.substring(0, sealed.indexOf(':') + 1);
        byte[] payload = Base64.getDecoder().decode(sealed.substring(prefix.length()));
        payload[payload.length - 1] ^= 0x01;
        String tampered = prefix + Base64.getEncoder().encodeToString(payload);
        assertThrows(IllegalStateException.class, () -> vault.open(tampered));
    }

    @Test
    void nullPassesThrough() {
        assertNull(vault.seal(null));
        assertNull(vault.open(null));
    }

    @Test
    void refusesToOpenPlainValues() {
        assertThrows(IllegalArgumentException.class, () -> vault.open("900-12-3456"));
    }
}
