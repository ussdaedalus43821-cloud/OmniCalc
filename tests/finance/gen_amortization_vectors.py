#!/usr/bin/env python3
"""Reference schedules for tests/finance/amortization_test.nova.

Run `python3 tests/finance/gen_amortization_vectors.py` to regenerate. It
prints the summary values the test checks inline, and writes the full
canonical schedule to tests/finance/vectors/mortgage_200k_6_5_360.json for
a row-by-row diff.

It is a separate Python implementation of the rules in CLAUDE.md
"Amortization rules", using fractions.Fraction and integer minor units:
  - interest each period = balance * rate, rounded half-up (away from zero);
  - a regular period pays `payment` (+ extra + any lump sum);
  - if that would clear the balance, or this is the last period, the period
    is the final row: it pays exactly balance + interest, and the difference
    from the scheduled amount is recorded as `adjustment`.
Payments use TVM's closed form (decimal, ROUND_HALF_UP), the same way
gen_tvm_vectors.py does.
"""

import json
import os
from decimal import ROUND_HALF_UP, Decimal, getcontext
from fractions import Fraction

getcontext().prec = 80
MICRO = 1000000
HERE = os.path.dirname(os.path.abspath(__file__))


def half_up(fraction):
    """Fraction -> int, halves away from zero."""
    sign = -1 if fraction < 0 else 1
    magnitude = abs(fraction)
    return sign * int((magnitude.numerator * 2 + magnitude.denominator) // (2 * magnitude.denominator))


def tvm_payment(principal, annual_micro, periods_per_year, n):
    r = Decimal(annual_micro) / Decimal(MICRO) / Decimal(periods_per_year)
    g = (1 + r) ** n
    exact = Decimal(principal) * r * g / (g - 1)
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def schedule(principal, rate, n, payment, extra=0, lumps=None):
    """Rows {period, payment, interest, principal, balance, regular, extra,
    adjustment, kind}, where payment = regular + extra + adjustment."""
    lumps = lumps or {}
    rows = []
    balance = principal
    for period in range(1, n + 1):
        interest = half_up(balance * rate)
        due = balance + interest
        extra_here = extra + lumps.get(period, 0)
        scheduled = payment + extra_here
        final = scheduled >= due or period == n
        paid = due if final else scheduled
        principal_part = paid - interest
        balance -= principal_part
        rows.append({
            "period": period, "payment": paid, "interest": interest,
            "principal": principal_part, "balance": balance,
            "regular": payment, "extra": extra_here, "adjustment": paid - scheduled,
            "kind": "final" if final else "regular",
        })
        if final:
            break
    return rows


def totals(rows):
    return {
        "total_paid": sum(r["payment"] for r in rows),
        "total_interest": sum(r["interest"] for r in rows),
        "payoff_period": rows[-1]["period"],
    }


def show(label, value):
    print("{:<46} {}".format(label, value))


def main():
    monthly_65 = Fraction(65000, 12 * MICRO)

    # 1. Canonical: 200,000.00 at 6.5%/12, 360 months, payment 1,264.14.
    pay = tvm_payment(20000000, 65000, 12, 360)
    rows = schedule(20000000, monthly_65, 360, pay)
    show("canonical payment", pay)
    show("canonical row 1", rows[0])
    show("canonical row 360", rows[-1])
    show("canonical totals", totals(rows))
    path = os.path.join(HERE, "vectors", "mortgage_200k_6_5_360.json")
    with open(path, "w") as handle:
        json.dump([[r["period"], r["payment"], r["interest"], r["principal"], r["balance"]] for r in rows],
                  handle, separators=(",", ":"))
        handle.write("\n")
    show("wrote", os.path.relpath(path, os.path.dirname(os.path.dirname(HERE))))

    # 2. 300,000.00 at 6.5%/12: the exact payment 1,896.204... rounds DOWN.
    pay2 = tvm_payment(30000000, 65000, 12, 360)
    rows2 = schedule(30000000, monthly_65, 360, pay2)
    show("300k payment", pay2)
    show("300k row 360", rows2[-1])
    show("300k totals", totals(rows2))

    # 3. Canonical + extra of payment // 12 every month.
    extra = pay // 12
    rows3 = schedule(20000000, monthly_65, 360, pay, extra=extra)
    show("extra per month", extra)
    show("extra: last row", rows3[-1])
    show("extra: totals", totals(rows3))

    # 4. Canonical + lump sums of 10,000.00 at periods 12 and 60.
    rows4 = schedule(20000000, monthly_65, 360, pay, lumps={12: 1000000, 60: 1000000})
    show("lumps: row 12", rows4[11])
    show("lumps: last row", rows4[-1])
    show("lumps: totals", totals(rows4))

    # 5. Biweekly: rate 6.5%/26 per period, half the monthly payment,
    #    at most ceil(360 * 26 / 12) = 780 periods.
    biweekly_rate = Fraction(65000, 26 * MICRO)
    half = half_up(Fraction(pay, 2))
    rows5 = schedule(20000000, biweekly_rate, 780, half)
    show("biweekly payment", half)
    show("biweekly last row", rows5[-1])
    show("biweekly totals", totals(rows5))
    show("biweekly payoff in years", Fraction(rows5[-1]["period"], 26))
    show("monthly+extra payoff in years", Fraction(rows3[-1]["period"], 12))

    # 6. Zero rate: 1,200.00 over 12 periods at 100.00.
    rows6 = schedule(120000, Fraction(0), 12, 10000)
    show("zero-rate totals", totals(rows6))


if __name__ == "__main__":
    main()
