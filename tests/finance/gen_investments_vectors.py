#!/usr/bin/env python3
"""Reference values for tests/finance/investments_test.nova.

Run `python3 tests/finance/gen_investments_vectors.py` to regenerate. A separate
implementation: fractions for shares and money (cost basis and value are
sum(shares * price), rounded half-up to the cent ONCE), 50-digit decimal for
CAGR = (final / initial) ** (1 / years) - 1, and the largest-remainder method
for allocation weights in basis points.

Excel reference: Microsoft's RRI example, =RRI(96, 10000, 11000) = 0.0009933
(support.microsoft.com, "RRI function"); RRI(n, pv, fv) = (fv / pv)^(1/n) - 1,
which is CAGR with n periods.
"""

from decimal import Decimal, getcontext
from fractions import Fraction

getcontext().prec = 50


def half_up(f):
    sign = -1 if f < 0 else 1
    m = abs(Fraction(f))
    return sign * ((2 * m.numerator + m.denominator) // (2 * m.denominator))


def cagr(initial, final, years):
    years = Fraction(years)
    exponent = Decimal(years.denominator) / Decimal(years.numerator)
    return (Decimal(final) / Decimal(initial)) ** exponent - 1


def allocation_bp(values):
    total = sum(values)
    exact = [Fraction(v * 10000, total) for v in values]
    floors = [int(e) for e in exact]
    remaining = 10000 - sum(floors)
    order = sorted(range(len(values)), key=lambda i: (-(exact[i] - floors[i]), i))
    for i in order[:remaining]:
        floors[i] += 1
    return floors


def show(label, value):
    print("{:<52} {}".format(label, value))


def main():
    # lots: (shares as Fraction, price per share in cents)
    single = [(Fraction(10), 15000)]
    show("single lot 10 @ 150.00: cost / value @ 172.35", (half_up(sum(s * p for s, p in single)), half_up(Fraction(10) * 17235)))
    lots = [(Fraction(10), 15000), (Fraction(5), 18000), (Fraction(12, 5), 21050)]
    cost = sum(s * p for s, p in lots)
    shares = sum(s for s, _ in lots)
    show("3 lots: total shares", shares)
    show("3 lots: cost basis (cents)", half_up(cost))
    show("3 lots: average cost per share (cents, half-up)", half_up(cost / shares))
    show("3 lots: value @ 195.17", half_up(shares * 19517))
    show("3 lots: unrealized gain", half_up(shares * 19517) - half_up(cost))
    show("0.5 shares @ 100.00: cost", half_up(Fraction(1, 2) * 10000))
    show("0.333333 shares @ 299.99: cost", half_up(Fraction(333333, 1000000) * 29999))

    show("CAGR doubling in 10 years", cagr(1, 2, 10))
    show("CAGR halving in 5 years", cagr(2, 1, 5))
    show("CAGR one year 100 -> 112.50", cagr(10000, 11250, 1))
    show("CAGR 10,000 -> 11,000 over 96 periods (RRI)", cagr(10000, 11000, 96))
    show("CAGR 10,000 -> 15,000 over 1,000 days / 365", cagr(10000, 15000, Fraction(1000, 365)))

    values = [123456, 654321, 222222]
    show("allocation bp of 1,234.56 / 6,543.21 / 2,222.22", allocation_bp(values))
    show("allocation bp of three equal values", allocation_bp([100, 100, 100]))


if __name__ == "__main__":
    main()
