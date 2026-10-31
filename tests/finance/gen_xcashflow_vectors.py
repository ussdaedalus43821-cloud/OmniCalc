#!/usr/bin/env python3
"""Reference values for the XNPV/XIRR checks in tests/finance/cashflow_test.nova.

Run `python3 tests/finance/gen_xcashflow_vectors.py` to regenerate. A separate
implementation: Python's decimal module at 50 digits, where Decimal ** Decimal
is correctly rounded, so (1 + r) ** (days / 365) is computed far more precisely
than the binary floats cashflow.nova uses. Day counts come from datetime.date
(actual days), and halves round away from zero.

Also checked against Microsoft's published XNPV/XIRR documentation example
(support.microsoft.com, "XNPV function" / "XIRR function"): the flows
-10,000 (2008-01-01), 2,750 (2008-03-01), 4,250 (2008-10-30), 3,250 (2009-02-15)
and 2,750 (2009-04-01) give XNPV(9%) = $2,086.65 and XIRR = 0.373362535.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, getcontext
from fractions import Fraction

getcontext().prec = 50


def xnpv(rate, flows):
    start = flows[0][0]
    g = 1 + rate
    return sum(Decimal(amount) / g ** (Decimal((day - start).days) / 365) for day, amount in flows)


def half_up(value):
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def xirr(flows, lo, hi):
    f_lo = xnpv(lo, flows)
    assert f_lo * xnpv(hi, flows) < 0
    for _ in range(170):
        mid = (lo + hi) / 2
        f_mid = xnpv(mid, flows)
        if (f_mid < 0) == (f_lo < 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def as_rate(value):
    """{num, den} with value = num / (den * 1e6), den = 1e24."""
    num = int((Fraction(value) * 10 ** 30).limit_denominator(1) + Fraction(1, 2))
    return "{{num: {}, den: {}}}".format(num, 10 ** 24)


def show(label, value):
    print("{:<46} {}".format(label, value))


def main():
    D = Decimal
    excel = [(date(2008, 1, 1), -1000000), (date(2008, 3, 1), 275000), (date(2008, 10, 30), 425000),
             (date(2009, 2, 15), 325000), (date(2009, 4, 1), 275000)]
    show("excel xnpv at 9% (cents)", half_up(xnpv(D("0.09"), excel)))
    show("excel xirr", xirr(excel, D("0.1"), D("1")))
    show("  as {num, den}", as_rate(xirr(excel, D("0.1"), D("1"))))

    start = date(2024, 1, 15)
    gaps = [(start, -1000000), (date.fromordinal(start.toordinal() + 30), 200000),
            (date.fromordinal(start.toordinal() + 75), 300000), (date.fromordinal(start.toordinal() + 475), 650000)]
    show("gaps 30/45/400 days: dates", [d.isoformat() for d, _ in gaps])
    show("gaps: xnpv at 7% (cents)", half_up(xnpv(D("0.07"), gaps)))
    show("gaps: xirr as {num, den}", as_rate(xirr(gaps, D("0.01"), D("1"))))

    pair = [(start, -100000), (date.fromordinal(start.toordinal() + 180), 105000)]
    exact = D("1.05") ** (D(365) / D(180)) - 1
    show("180-day pair: xirr = 1.05^(365/180) - 1", exact)
    show("  as {num, den}", as_rate(exact))

    # Round trip at scale 6: choose the first flow so XNPV at 8% is zero.
    later = [(date.fromordinal(start.toordinal() + 100), 3000000000),
             (date.fromordinal(start.toordinal() + 250), 4000000000),
             (date.fromordinal(start.toordinal() + 700), 5000000000)]
    g = D("1.08")
    first = -half_up(sum(D(a) / g ** (D((d - start).days) / 365) for d, a in later))
    show("scale-6 round trip: first flow (micro-dollars)", first)


if __name__ == "__main__":
    main()
