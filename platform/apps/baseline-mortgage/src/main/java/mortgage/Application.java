package mortgage;

import java.math.BigDecimal;

/** The figures underwriting needs from a case. */
public record Application(
        BigDecimal loanAmount,
        BigDecimal appraisedValue,
        BigDecimal annualIncome,
        BigDecimal monthlyDebt,
        BigDecimal proposedMonthlyPayment) {
}
