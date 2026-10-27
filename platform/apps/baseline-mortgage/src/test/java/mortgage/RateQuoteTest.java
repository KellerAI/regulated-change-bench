package mortgage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class RateQuoteTest {

    @Test
    void thirtyYearPaymentMatchesTheAmortisationTable() {
        RateQuote quote = RateQuote.price(new BigDecimal("300000"), new BigDecimal("400000"), 30, Fixtures.START);
        assertEquals(new BigDecimal("6.250"), quote.ratePercent());
        assertEquals(new BigDecimal("1847.15"), quote.monthlyPayment());
        assertEquals(Fixtures.START, quote.quotedAt());
    }

    @Test
    void shortTermsPriceLower() {
        RateQuote quote = RateQuote.price(new BigDecimal("200000"), new BigDecimal("400000"), 15, Fixtures.START);
        assertEquals(new BigDecimal("5.750"), quote.ratePercent());
        assertEquals(new BigDecimal("1660.82"), quote.monthlyPayment());
    }

    @Test
    void highLoanToValuePricesHigher() {
        RateQuote quote = RateQuote.price(new BigDecimal("380000"), new BigDecimal("400000"), 30, Fixtures.START);
        assertEquals(new BigDecimal("6.625"), quote.ratePercent());
        assertEquals(new BigDecimal("2433.18"), quote.monthlyPayment());
    }

    @Test
    void zeroRateSplitsPrincipalEvenly() {
        assertEquals(new BigDecimal("1000.00"), RateQuote.monthlyPayment(new BigDecimal("360000"), BigDecimal.ZERO, 30));
    }

    @Test
    void unsupportedTermsAreRejected() {
        ServiceException refused = assertThrows(ServiceException.class,
                () -> RateQuote.price(new BigDecimal("200000"), new BigDecimal("400000"), 25, Fixtures.START));
        assertEquals(ServiceException.VALIDATION, refused.code());
    }
}
