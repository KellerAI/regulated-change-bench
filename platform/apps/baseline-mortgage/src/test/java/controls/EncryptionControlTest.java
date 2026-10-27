package controls;

import static org.junit.jupiter.api.Assertions.assertTrue;

import mortgage.CaseStore;
import mortgage.LoanCase;
import mortgage.NpiRegistry;
import mortgage.NpiVault;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

@Tag("control")
class EncryptionControlTest {

    private static final String CASE_ID = "HW-900001";

    @TempDir
    Path directory;

    @Test
    @Control(obligation = "ENC-1", coverage = "exhaustive", domain = "mortgage.npi_registry")
    @SuppressWarnings("unchecked")
    void everyNpiFieldIsSealedAtRest() throws IOException {
        Set<String> approved = Set.copyOf(PolicyFiles.strings(PolicyFiles.params(), "mortgage.npi_fields"));
        List<String> violations = new ArrayList<>();
        for (String field : approved) {
            if (!NpiRegistry.FIELDS.contains(field)) {
                violations.add(field + " is approved NPI but missing from NpiRegistry");
            }
        }
        Set<String> fields = new TreeSet<>(approved);
        fields.addAll(NpiRegistry.FIELDS);

        NpiVault vault = new NpiVault();
        Path file = directory.resolve("cases.json");
        CaseStore store = CaseStore.atPath(file, vault);
        store.save(caseWithMarkers(fields));

        String fileText = Files.readString(file, StandardCharsets.UTF_8);
        Map<String, Object> applicant = (Map<String, Object>) store.atRest(CASE_ID).get("applicant");
        for (String field : fields) {
            checkSealed(field, applicant.get(field), fileText, vault, violations);
        }
        LoanCase reloaded = CaseStore.atPath(file, vault).find(CASE_ID).orElseThrow();
        for (String field : fields) {
            if (!marker(field).equals(reloaded.applicantField(field))) {
                violations.add(field + " does not read back after a reload");
            }
        }
        assertTrue(violations.isEmpty(), "NPI not sealed at rest: " + violations);
    }

    private static LoanCase caseWithMarkers(Set<String> fields) {
        LoanCase loanCase = new LoanCase(CASE_ID, null, "enc-probe", ControlFixtures.START);
        loanCase.putApplicantField("full_name", "Enc Probe");
        for (String field : fields) {
            loanCase.putApplicantField(field, marker(field));
        }
        return loanCase;
    }

    private static void checkSealed(String field, Object stored, String fileText, NpiVault vault, List<String> violations) {
        String plaintext = marker(field);
        if (fileText.contains(plaintext)) {
            violations.add(field + " appears in clear in the case file");
        }
        if (!(stored instanceof String) || !NpiVault.isSealed((String) stored)) {
            violations.add(field + " is stored unsealed");
            return;
        }
        String sealed = (String) stored;
        if (payloadContains(sealed, plaintext)) {
            violations.add(field + " sealed value carries the plaintext");
        }
        if (!plaintext.equals(vault.open(sealed))) {
            violations.add(field + " does not open to the stored value");
        }
    }

    private static boolean payloadContains(String sealed, String plaintext) {
        byte[] payload = Base64.getDecoder().decode(sealed.substring(sealed.indexOf(':') + 1));
        return new String(payload, StandardCharsets.ISO_8859_1).contains(plaintext);
    }

    private static String marker(String field) {
        return "enc-marker-" + field + "-7319";
    }
}
