package mortgage;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** Authenticated encryption (AES-256-GCM) for NPI values stored at rest. */
public final class NpiVault {

    /** Synthetic development key. Deployed environments load the key from the bank's KMS. */
    private static final String DEVELOPMENT_KEY_HEX = "5f1c2e8a9b3d4c7e6a0f1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f6a";
    private static final String PREFIX = "gcm1:";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;

    private final SecretKey key;
    private final SecureRandom random;

    public NpiVault() {
        this(new SecureRandom());
    }

    public NpiVault(SecureRandom random) {
        this.key = new SecretKeySpec(HexFormat.of().parseHex(DEVELOPMENT_KEY_HEX), "AES");
        this.random = random;
    }

    public String seal(String plaintext) {
        if (plaintext == null) {
            return null;
        }
        byte[] iv = new byte[IV_BYTES];
        random.nextBytes(iv);
        byte[] ciphertext = run(Cipher.ENCRYPT_MODE, iv, plaintext.getBytes(StandardCharsets.UTF_8));
        byte[] payload = Arrays.copyOf(iv, IV_BYTES + ciphertext.length);
        System.arraycopy(ciphertext, 0, payload, IV_BYTES, ciphertext.length);
        return PREFIX + Base64.getEncoder().encodeToString(payload);
    }

    public String open(String sealed) {
        if (sealed == null) {
            return null;
        }
        if (!isSealed(sealed)) {
            throw new IllegalArgumentException("Value is not sealed");
        }
        byte[] payload = Base64.getDecoder().decode(sealed.substring(PREFIX.length()));
        byte[] iv = Arrays.copyOfRange(payload, 0, IV_BYTES);
        byte[] ciphertext = Arrays.copyOfRange(payload, IV_BYTES, payload.length);
        return new String(run(Cipher.DECRYPT_MODE, iv, ciphertext), StandardCharsets.UTF_8);
    }

    public static boolean isSealed(String value) {
        return value != null && value.startsWith(PREFIX);
    }

    private byte[] run(int mode, byte[] iv, byte[] input) {
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(mode, key, new GCMParameterSpec(TAG_BITS, iv));
            return cipher.doFinal(input);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("NPI vault operation failed", e);
        }
    }
}
