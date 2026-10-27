package mortgage;

import java.math.BigDecimal;

/** Credit approval authority by loan amount, and the maker-checker rule. */
public final class Approvals {

    private Approvals() {
    }

    /** How many distinct approvers a loan needs and the lowest role that may approve it. */
    public record Requirement(Role minimumRole, int approvers) {

        public boolean allows(Role role) {
            if (minimumRole == Role.UNDERWRITER) {
                return role == Role.UNDERWRITER || role == Role.SENIOR_UNDERWRITER;
            }
            return role == minimumRole;
        }
    }

    public static Requirement requiredApprovals(BigDecimal amount) {
        if (amount.compareTo(Policy.UNDERWRITER_LIMIT) <= 0) {
            return new Requirement(Role.UNDERWRITER, 1);
        }
        if (amount.compareTo(Policy.SENIOR_LIMIT) <= 0) {
            return new Requirement(Role.SENIOR_UNDERWRITER, 1);
        }
        return new Requirement(Role.SENIOR_UNDERWRITER, 2);
    }

    /**
     * Records the actor's approval. Returns true once the case has all the approvals its
     * amount requires.
     */
    public static boolean approve(LoanCase loanCase, Actor actor) {
        if (actor.userId().equals(loanCase.preparedBy())) {
            throw new ServiceException(ServiceException.MAKER_CHECKER, "The preparer of a case cannot approve it");
        }
        Requirement requirement = requiredApprovals(loanCase.loanAmount());
        if (!requirement.allows(actor.role())) {
            throw new ServiceException(ServiceException.AUTHORITY, "Loan amount exceeds the approver's authority");
        }
        if (loanCase.approvers().contains(actor.userId())) {
            throw new ServiceException(ServiceException.DUPLICATE, "This approver has already approved the case");
        }
        loanCase.addApprover(actor.userId());
        return loanCase.approvers().size() >= requirement.approvers();
    }
}
