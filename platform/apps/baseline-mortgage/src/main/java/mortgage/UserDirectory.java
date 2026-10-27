package mortgage;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/** Staff and applicant accounts and their roles. */
public final class UserDirectory {

    private final Map<String, Role> roles = new ConcurrentHashMap<>();
    private final AuditLog audit;

    public UserDirectory(AuditLog audit) {
        this.audit = audit;
    }

    /** Registers an account at start-up, before any administrator is signed in. */
    public void bootstrap(String userId, Role role) {
        roles.put(userId, role);
    }

    public void assignRole(Actor actor, String userId, Role role) {
        if (!AccessMatrix.isAllowed(actor.role(), Action.MANAGE_USERS)) {
            throw new ServiceException(ServiceException.FORBIDDEN, "Not permitted: " + Action.MANAGE_USERS);
        }
        if (actor.userId().equals(userId)) {
            throw new ServiceException(ServiceException.FORBIDDEN, "Administrators cannot change their own role");
        }
        roles.put(userId, role);
        audit.record(actor, Action.MANAGE_USERS, userId, "role_assigned:" + role);
    }

    public Optional<Role> roleOf(String userId) {
        return Optional.ofNullable(roles.get(userId));
    }
}
