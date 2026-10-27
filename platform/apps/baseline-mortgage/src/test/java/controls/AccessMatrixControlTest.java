package controls;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import mortgage.AccessMatrix;
import mortgage.Action;
import mortgage.Role;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("control")
class AccessMatrixControlTest {

    @Test
    @Control(obligation = "ACC-1", coverage = "exhaustive", domain = "mortgage.roles_x_actions")
    void matrixEqualsApprovedPolicy() {
        Map<String, Object> policy = PolicyFiles.accessPolicy();
        Set<String> approvedRoles = new TreeSet<>(PolicyFiles.strings(policy, "roles"));
        Set<String> approvedActions = new TreeSet<>(PolicyFiles.strings(policy, "actions"));
        assertEquals(approvedRoles, names(Role.values()), "roles differ from the approved policy");
        assertEquals(approvedActions, names(Action.values()), "actions differ from the approved policy");
        Map<String, Object> matrix = PolicyFiles.object(policy, "matrix");
        List<String> differences = new ArrayList<>();
        for (Role role : Role.values()) {
            Map<String, Object> approvedRow = PolicyFiles.object(matrix, role.name());
            for (Action action : Action.values()) {
                Object approved = approvedRow.get(action.name());
                assertTrue(approved instanceof Boolean, "approved policy must state " + role + " x " + action + " explicitly");
                boolean allowed = AccessMatrix.isAllowed(role, action);
                if (allowed != (Boolean) approved) {
                    differences.add(role + " x " + action + ": code=" + allowed + ", approved=" + approved);
                }
            }
        }
        assertTrue(differences.isEmpty(), "access matrix differs from the approved policy: " + differences);
    }

    @Test
    @Control(obligation = "ACC-2", coverage = "exhaustive", domain = "mortgage.actions")
    void auditorIsReadOnly() {
        Map<String, Object> policy = PolicyFiles.accessPolicy();
        Set<String> approvedStateChanging = Set.copyOf(PolicyFiles.strings(policy, "state_changing_actions"));
        List<String> violations = new ArrayList<>();
        for (String auditorRole : PolicyFiles.strings(policy, "auditor_roles")) {
            Role role = Role.valueOf(auditorRole);
            for (Action action : Action.values()) {
                boolean changesState = action.isStateChanging() || approvedStateChanging.contains(action.name());
                if (changesState && AccessMatrix.isAllowed(role, action)) {
                    violations.add(role + " may " + action);
                }
            }
        }
        assertTrue(violations.isEmpty(), "auditor roles hold state-changing actions: " + violations);
    }

    @Test
    @Control(obligation = "SOD-1", coverage = "exhaustive", domain = "mortgage.actions")
    void adminCannotApproveCredit() {
        Map<String, Object> policy = PolicyFiles.accessPolicy();
        Set<String> creditDecisions = Set.copyOf(PolicyFiles.strings(policy, "credit_decision_actions"));
        List<String> violations = new ArrayList<>();
        for (String adminRole : PolicyFiles.strings(policy, "it_admin_roles")) {
            Role role = Role.valueOf(adminRole);
            for (Action action : Action.values()) {
                if (creditDecisions.contains(action.name()) && AccessMatrix.isAllowed(role, action)) {
                    violations.add(role + " may " + action);
                }
            }
        }
        assertTrue(violations.isEmpty(), "IT administrator roles hold credit decisions: " + violations);
    }

    private static Set<String> names(Enum<?>[] values) {
        Set<String> names = new TreeSet<>();
        for (Enum<?> value : values) {
            names.add(value.name());
        }
        return names;
    }
}
