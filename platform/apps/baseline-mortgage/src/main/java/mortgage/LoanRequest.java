package mortgage;

import java.math.BigDecimal;

/** Requested loan terms. A null component means "leave unchanged" when editing. */
public record LoanRequest(BigDecimal loanAmount, BigDecimal appraisedValue, BigDecimal monthlyDebt) {
}
