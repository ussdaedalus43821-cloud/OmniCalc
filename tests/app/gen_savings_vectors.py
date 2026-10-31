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


def show(label, value):
    print("{:<52} {}".format(label, value))


def main():
    show("10,000 + 500/month, 7%, 30 years: FV (cents)", fv(1000000, 50000, "7", 360))
    show("  year 1 balance", fv(1000000, 50000, "7", 12))
    show("  year 10 balance", fv(1000000, 50000, "7", 120))
    show("0 + 200/month, 0%, 5 years: FV", fv(0, 20000, "0", 60))
    show("5,000 + 0/month, -2%, 3 years: FV", fv(500000, 0, "-2", 36))


if __name__ == "__main__":
    main()
