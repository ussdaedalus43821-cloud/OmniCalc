#!/usr/bin/env python3
"""Reference plans for tests/finance/debt_payoff_test.nova.

Run `python3 tests/finance/gen_debt_payoff_vectors.py` to regenerate. A separate
Python implementation (fractions, integer cents) of CLAUDE.md "Debt payoff
convention":
  each month: (1) every open debt accrues interest = balance * monthly rate,
  rounded half-up to the cent; (2) every open debt gets its minimum (or its
  balance, if smaller); (3) the rest of the budget goes to the first open debt
  in strategy order, cascading to the next one in the same month when it is
  cleared. The total paid is the whole budget every month but the last, so a
  paid-off debt's minimum "rolls" into the target.
  Order: snowball = balance ascending, avalanche = rate descending; ties keep
  input order. Rates are APR / 12.
"""

from fractions import Fraction


def half_up(f):
    sign = -1 if f < 0 else 1
    m = abs(f)
    return sign * ((2 * m.numerator + m.denominator) // (2 * m.denominator))


def plan(debts, budget, strategy):
    rates = [Fraction(apr_micro, 12 * 1000000) for _, _, apr_micro, _ in debts]
    index = list(range(len(debts)))
    if strategy == "snowball":
        order = sorted(index, key=lambda i: (debts[i][1], i))
    else:
        order = sorted(index, key=lambda i: (-rates[i], i))
    balance = [d[1] for d in debts]
    interest = [0] * len(debts)
    paid_off = [0] * len(debts)
    month, total_paid = 0, 0
    while any(balance):
        month += 1
        assert month <= 1200
        for i in index:
            if balance[i]:
                charge = half_up(balance[i] * rates[i])
                balance[i] += charge
                interest[i] += charge
        available = budget
        for i in index:
            if balance[i]:
                pay = min(debts[i][3], balance[i])
                balance[i] -= pay
                available -= pay
        for i in order:
            if balance[i] and available:
                pay = min(available, balance[i])
                balance[i] -= pay
                available -= pay
        total_paid += budget - available
        for i in index:
            if balance[i] == 0 and paid_off[i] == 0:
                paid_off[i] = month
    return {
        "order": [debts[i][0] for i in order],
        "payoff_months": month,
        "total_interest": sum(interest),
        "total_paid": total_paid,
        "per_debt": [(debts[i][0], paid_off[i], interest[i]) for i in index],
    }


def show(label, value):
    print("{:<34} {}".format(label, value))


def main():
    # name, balance (cents), APR (micro-units), minimum (cents)
    three = [("Medical", 120000, 0, 5000), ("Card", 600000, 249900, 15000), ("Car", 900000, 70000, 25000)]
    for strategy in ["snowball", "avalanche"]:
        show("3 debts, budget 700, " + strategy, plan(three, 70000, strategy))
    same_rate = [("Big", 900000, 180000, 20000), ("Mid", 400000, 180000, 10000), ("Small", 150000, 180000, 4000)]
    for strategy in ["snowball", "avalanche"]:
        show("equal 18% rates, " + strategy, plan(same_rate, 60000, strategy))
    realistic = [("Store card", 150000, 269900, 4000), ("Visa", 850000, 219900, 17000),
                 ("Personal loan", 500000, 119900, 16000), ("Car", 1400000, 59900, 33000)]
    for strategy in ["snowball", "avalanche"]:
        show("realistic 4 debts, " + strategy, plan(realistic, 100000, strategy))


if __name__ == "__main__":
    main()
