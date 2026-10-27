package mortgage;

import java.time.Instant;

/** A free-text note left on a case by a user. */
public record CaseNote(String author, String text, Instant createdAt) {

    public static final int MAX_LENGTH = 2000;

    public static CaseNote of(String author, String text, Instant createdAt) {
        if (text == null || text.isBlank()) {
            throw new ServiceException(ServiceException.VALIDATION, "Note text is required");
        }
        if (text.length() > MAX_LENGTH) {
            throw new ServiceException(ServiceException.VALIDATION, "Note is longer than " + MAX_LENGTH + " characters");
        }
        return new CaseNote(author, text.strip(), createdAt);
    }
}
