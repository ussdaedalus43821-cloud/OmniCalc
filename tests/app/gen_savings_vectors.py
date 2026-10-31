#!/usr/bin/env python3
"""Reference values for tests/app/savings_screen_test.nova.

Run `python3 tests/app/gen_savings_vectors.py` to regenerate. Independent of
tvm.nova: 80-digit decimal with the textbook future-value formula,
contributions at the END of each month (an ordinary annuity), rate = annual / 12,
and the balance rounded half-up to the cent:
    FV = P * (1 + r)^n + C * ((1 + r)^n - 1) / r      (n = 12 * years)
"""

from decimal import ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 80


def fv(initial, contribution, annual_percent, months):
    r = Decimal(annual_percent) / 100 / 12
    g = (1 + r) ** months
    annuity = Decimal(months) if r == 0 else (g - 1) / r
    return int((Decimal(initial) * g + Decimal(contribution) * annuity).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def pmt_needed(initial, target, annual_percent, months):
    """Monthly end-of-month contribution reaching `target`, rounded half-up."""
    r = Decimal(annual_percent) / 100 / 12
    g = (1 + r) ** months
    annuity = Decimal(months) if r == 0 else (g - 1) / r
    return int(((Decimal(target) - Decimal(initial) * g) / annuity).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def months_needed(initial, contribution, annual_percent, target):
    """Real-valued months to reach `target`: n = ln((C + T r) / (C + P r)) / ln(1 + r)."""
    r = Decimal(annual_percent) / 100 / 12
    if r == 0:
        return (Decimal(target) - Decimal(initial)) / Decimal(contribution)
    return ((Decimal(contribution) + Decimal(target) * r) / (Decimal(contribution) + Decimal(initial) * r)).ln() / (1 + r).ln()


def show(label, value):
    print("{:<52} {}".format(label, value))


def main():
    show("10,000 + 500/month, 7%, 30 years: FV (cents)", fv(1000000, 50000, "7", 360))
    show("  year 1 balance", fv(1000000, 50000, "7", 12))
    show("  year 10 balance", fv(1000000, 50000, "7", 120))
    show("0 + 200/month, 0%, 5 years: FV", fv(0, 20000, "0", 60))
    show("5,000 + 0/month, -2%, 3 years: FV", fv(500000, 0, "-2", 36))
    # Solve for the contribution: 10,000 initial, 7%, 30 years, target 1,000,000.00.
    need = pmt_needed(1000000, 100000000, "7", 360)
    show("contribution needed for 1,000,000 in 30y at 7%", need)
    show("  FV with that rounded contribution", fv(1000000, need, "7", 360))
    # Solve for time: 10,000 initial + 500/month at 7% to reach 250,000.00.
    exact = months_needed(1000000, 50000, "7", 25000000)
    show("months to 250,000 with 500/month at 7% (exact)", exact)
    show("  FV at 240 months", fv(1000000, 50000, "7", 240))
    show("  FV at 241 months", fv(1000000, 50000, "7", 241))


if __name__ == "__main__":
    main()
