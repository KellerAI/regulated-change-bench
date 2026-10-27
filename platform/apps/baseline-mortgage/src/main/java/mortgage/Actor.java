package mortgage;

/** The authenticated caller of a service operation. */
public record Actor(String userId, Role role) {
}
