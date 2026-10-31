#!/usr/bin/env python3
"""Reference values for tests/finance/cashflow_test.nova.

Run `python3 tests/finance/gen_cashflow_vectors.py` to regenerate. It is a
separate implementation: NPV summed term by term (no polynomial tricks) -
in exact fractions for the short flows, in 60-digit decimal for the
360-payment schedules, where exact fractions are too slow - IRR by
bisection on that NPV, and payback by walking the running total. Schedules
come from gen_amortization_vectors.py (the same rules as
src/finance/amortization.nova).
"""

import os
import sys
from decimal import Decimal, getcontext
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_amortization_vectors import half_up, schedule, tvm_payment  # noqa: E402

MICRO = 1000000
getcontext().prec = 60


def npv(rate, flows):
    return sum(Fraction(amount) / (1 + rate) ** period for period, amount in flows)


def npv_decimal(rate, flows):
    g = 1 + rate
    return sum(Decimal(amount) / g ** period for period, amount in flows)


def irr(flows, lo, hi, value=npv, steps=200):
    f_lo = value(lo, flows)
    assert f_lo * value(hi, flows) < 0, "no sign change in the bracket"
    for _ in range(steps):
        mid = (lo + hi) / 2
        f_mid = value(mid, flows)
        if (f_mid < 0) == (f_lo < 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def as_rate(value):
    """{num, den} with value = num / (den * 1e6), den = 1e24."""
    exact = Fraction(value) if isinstance(value, Decimal) else value
    return "{{num: {}, den: {}}}".format(half_up(exact * Fraction(10) ** 30), 10 ** 24)


def schedule_irr(flows):
    lo, hi = Decimal(5416) / MICRO, Decimal(5418) / MICRO
    return irr(flows, lo, hi, value=npv_decimal, steps=120)


def schedule_flows(rows, principal):
    return [(0, principal)] + [(row["period"], -row["payment"]) for row in rows]


def show(label, value):
    print("{:<48} {}".format(label, value))


def main():
    ten = Fraction(1, 10)
    multi = [(0, -100000), (1, 30000), (2, 42000), (3, 68000), (5, 12000)]
    show("multi-flow npv at 10% (minor units)", half_up(npv(ten, multi)))
    show("multi-flow irr", as_rate(irr(multi, Fraction(0), Fraction(1))))

    payback_flows = [(0, -100000), (1, 30000), (2, 30000), (3, 50000)]
    total = 0
    for i, (period, amount) in enumerate(payback_flows):
        if i and total < 0 <= total + amount:
            prev = payback_flows[i - 1][0]
            show("payback (period, exact)", (period, prev + Fraction(period - prev) * -total / amount))
            break
        total += amount

    monthly = Fraction(65000, 12 * MICRO)
    pay = tvm_payment(20000000, 65000, 12, 360)
    canonical = schedule(20000000, monthly, 360, pay)
    r = schedule_irr(schedule_flows(canonical, 20000000))
    show("canonical schedule irr", as_rate(r))
    show("  minus 6.5%/12", float(Fraction(r) - monthly))

    extra = schedule(20000000, monthly, 360, pay, extra=pay // 12)
    r = schedule_irr(schedule_flows(extra, 20000000))
    show("extra-payment schedule irr", as_rate(r))
    show("  minus 6.5%/12", float(Fraction(r) - monthly))

    fine_pay = tvm_payment(200000000000, 65000, 12, 360)
    fine = schedule(200000000000, monthly, 360, fine_pay)
    r = schedule_irr(schedule_flows(fine, 200000000000))
    show("scale-6 schedule payment", fine_pay)
    show("scale-6 schedule irr", as_rate(r))
    show("scale-6 schedule irr minus 6.5%/12", float(Fraction(r) - monthly))


if __name__ == "__main__":
    main()
