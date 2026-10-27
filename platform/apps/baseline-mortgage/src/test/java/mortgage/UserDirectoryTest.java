package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class UserDirectoryTest {

    private final AuditLog audit = new AuditLog(new TestClock(Fixtures.START));
    private final UserDirectory users = new UserDirectory(audit);

    @Test
    void adminsAssignRolesAndTheChangeIsAudited() {
        users.assignRole(Fixtures.ADMIN, "uw-new", Role.UNDERWRITER);
        assertEquals(Role.UNDERWRITER, users.roleOf("uw-new").orElseThrow());
        AuditEvent event = audit.events().get(0);
        assertEquals(Action.MANAGE_USERS, event.action());
        assertEquals("uw-new", event.target());
    }

    @Test
    void othersCannotAssignRoles() {
        ServiceException refused = assertThrows(ServiceException.class,
                () -> users.assignRole(Fixtures.SENIOR, "uw-new", Role.UNDERWRITER));
        assertEquals(ServiceException.FORBIDDEN, refused.code());
    }

    @Test
    void adminsCannotChangeTheirOwnRole() {
        users.bootstrap(Fixtures.ADMIN.userId(), Role.ADMIN);
        assertThrows(ServiceException.class, () -> users.assignRole(Fixtures.ADMIN, Fixtures.ADMIN.userId(), Role.SENIOR_UNDERWRITER));
        assertEquals(Role.ADMIN, users.roleOf(Fixtures.ADMIN.userId()).orElseThrow());
    }
}
