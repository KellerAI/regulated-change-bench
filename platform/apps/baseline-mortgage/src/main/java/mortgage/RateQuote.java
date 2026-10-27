package mortgage;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Set;

/** An indicative fixed-rate quote and its monthly principal-and-interest payment. */
public record RateQuote(BigDecimal ratePercent, int termYears, BigDecimal monthlyPayment, Instant quotedAt) {

    static final BigDecimal BASE_RATE_PERCENT = new BigDecimal("6.250");
    static final BigDecimal HIGH_LTV_ADJUSTMENT = new BigDecimal("0.375");
    static final BigDecimal SHORT_TERM_ADJUSTMENT = new BigDecimal("-0.500");
    static final BigDecimal HIGH_LTV_THRESHOLD_PERCENT = new BigDecimal("80");
    static final Set<Integer> TERMS_YEARS = Set.of(15, 20, 30);

    private static final BigDecimal PERCENT_PER_MONTH_DIVISOR = new BigDecimal("1200");

    public static RateQuote price(BigDecimal loanAmount, BigDecimal appraisedValue, int termYears, Instant quotedAt) {
        if (!TERMS_YEARS.contains(termYears)) {
            throw new ServiceException(ServiceException.VALIDATION, "Unsupported term: " + termYears + " years");
        }
        BigDecimal ltvPercent = Underwriting.loanToValuePercent(loanAmount, appraisedValue);
        BigDecimal rate = rateFor(ltvPercent, termYears);
        BigDecimal payment = monthlyPayment(loanAmount, rate, termYears);
        return new RateQuote(rate, termYears, payment, quotedAt);
    }

    static BigDecimal rateFor(BigDecimal ltvPercent, int termYears) {
        BigDecimal rate = BASE_RATE_PERCENT;
        if (ltvPercent.compareTo(HIGH_LTV_THRESHOLD_PERCENT) > 0) {
            rate = rate.add(HIGH_LTV_ADJUSTMENT);
        }
        if (termYears == 15) {
            rate = rate.add(SHORT_TERM_ADJUSTMENT);
        }
        return rate;
    }

    /** Standard amortisation: P * r * (1 + r)^n / ((1 + r)^n - 1), rounded to cents. */
    static BigDecimal monthlyPayment(BigDecimal principal, BigDecimal ratePercent, int termYears) {
        int months = termYears * 12;
        BigDecimal monthlyRate = ratePercent.divide(PERCENT_PER_MONTH_DIVISOR, MathContext.DECIMAL64);
        if (monthlyRate.signum() == 0) {
            return principal.divide(BigDecimal.valueOf(months), 2, RoundingMode.HALF_UP);
        }
        BigDecimal growth = BigDecimal.ONE.add(monthlyRate).pow(months, MathContext.DECIMAL64);
        BigDecimal numerator = principal.multiply(monthlyRate).multiply(growth);
        BigDecimal denominator = growth.subtract(BigDecimal.ONE);
        return numerator.divide(denominator, 2, RoundingMode.HALF_UP);
    }
}
