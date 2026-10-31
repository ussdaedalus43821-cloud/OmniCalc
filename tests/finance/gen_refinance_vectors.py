#!/usr/bin/env python3
"""Reference values for tests/finance/refinance_test.nova.

Run `python3 tests/finance/gen_refinance_vectors.py` to regenerate. Schedules
and payments come from gen_amortization_vectors.py (fractions, half-up). The
comparison follows CLAUDE.md "Refinance convention":
  - new payment: TVM closed form on the current principal at the new rate and term;
    closing costs are paid at period 0 and NOT financed;
  - each month's saving = current payment - new payment, using each schedule's
    actual payments (final adjustment included) and 0 after a loan is paid off;
  - break-even month: smallest k >= 1 where the cumulative saving >= closing
    costs, or none;
  - total_savings: the savings summed over the shorter schedule, minus closing costs;
  - lifetime_savings: current total paid - (new total paid + closing costs).
"""

import os
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_amortization_vectors import schedule, tvm_payment  # noqa: E402

MICRO = 1000000


def compare(principal, current_annual, current_n, current_payment, new_annual, new_n, closing):
    current = schedule(principal, Fraction(current_annual, 12 * MICRO), current_n, current_payment)
    new_payment = tvm_payment(principal, new_annual, 12, new_n)
    new = schedule(principal, Fraction(new_annual, 12 * MICRO), new_n, new_payment)
    paid_current = [row["payment"] for row in current]
    paid_new = [row["payment"] for row in new]
    horizon = max(len(paid_current), len(paid_new))
    cumulative, break_even = 0, None
    for k in range(1, horizon + 1):
        cumulative += (paid_current[k - 1] if k <= len(paid_current) else 0) - (paid_new[k - 1] if k <= len(paid_new) else 0)
        if break_even is None and cumulative >= closing:
            break_even = k
    shorter = min(len(paid_current), len(paid_new))
    return {
        "new_payment": new_payment,
        "monthly_savings": current_payment - new_payment,
        "break_even_month": break_even,
        "total_savings": sum(paid_current[:shorter]) - sum(paid_new[:shorter]) - closing,
        "lifetime_savings": sum(paid_current) - (sum(paid_new) + closing),
        "payoff_current": len(paid_current),
        "payoff_new": len(paid_new),
        "current_total_paid": sum(paid_current),
        "new_total_paid": sum(paid_new),
    }


def show(label, value):
    print("{:<40} {}".format(label, value))


def main():
    show("canonical 6.5%->5.0%, 360->360, 6,000", compare(20000000, 65000, 360, 126414, 50000, 360, 600000))
    # Five years in: the canonical balance after month 60 (row 60),
    # 300 months left; refinance to 4.5% over a fresh 360 months, 4,000 closing.
    current = schedule(20000000, Fraction(65000, 12 * MICRO), 360, 126414)
    balance_60 = current[59]["balance"]
    show("balance after month 60", balance_60)
    show("5 yrs in: 300 left -> 4.5%/360, 4,000", compare(balance_60, 65000, 300, 126414, 45000, 360, 400000))
    show("30 -> 15 years at 5.0%, 6,000", compare(20000000, 65000, 360, 126414, 50000, 180, 600000))
    show("tiny saving, huge closing", compare(20000000, 65000, 360, 126414, 64000, 360, 10000000))


if __name__ == "__main__":
    main()
