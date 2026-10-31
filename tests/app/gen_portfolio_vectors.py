#!/usr/bin/env python3
"""A 20-position portfolio for tests/app/investments_screen_test.nova.

Run `python3 tests/app/gen_portfolio_vectors.py` to regenerate
tests/app/vectors/portfolio_20.json, which holds the input rows exactly as
typed AND every expected figure, so the NovaLang test reads both from one file.

A separate implementation of src/app/investments_screen.nova's conventions:
fractions for shares and money (cost and value rounded half-up once per
position), annualized return = CAGR (value / cost) ** (365 / days) - 1 for a
single dated lot and XIRR (50-digit decimal bisection, actual/365) for several,
portfolio return = XIRR over every lot, largest-remainder allocation, and
percentages at 2 decimals rounded half-up.
"""

import json
import os
from datetime import date
from decimal import Decimal, getcontext
from fractions import Fraction

getcontext().prec = 50
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = date(2025, 10, 31)


def half_up(f):
    f = Fraction(f)
    sign = -1 if f < 0 else 1
    m = abs(f)
    return sign * ((2 * m.numerator + m.denominator) // (2 * m.denominator))


def cents(text):
    return int(Fraction(text.replace(",", "")) * 100)


def xnpv(rate, flows):
    start = flows[0][0]
    return sum(Decimal(a) / (1 + rate) ** (Decimal((d - start).days) / 365) for d, a in flows)


def xirr(flows):
    flows = sorted(flows)
    lo, hi = Decimal("-0.99"), Decimal("10")
    f_lo = xnpv(lo, flows)
    assert f_lo * xnpv(hi, flows) < 0
    for _ in range(160):
        mid = (lo + hi) / 2
        f_mid = xnpv(mid, flows)
        if (f_mid < 0) == (f_lo < 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def percent2(rate):
    return half_up(Fraction(rate) * 10000)


def rows():
    """20 symbols; S03, S07, S12 and S18 have two lots; S20 has a fractional share count."""
    out = []
    for k in range(1, 21):
        symbol = "S%02d" % k
        shares = str(3 * k + 1) if k != 20 else "12.345678"
        cost = "%d.%02d" % (20 + 7 * k, (13 * k) % 100)
        price = "%d.%02d" % (22 + 8 * k - (k % 4) * 3, (29 * k) % 100)
        bought = date(2019 + k % 6, 1 + k % 12, 1 + (5 * k) % 28)
        out.append([symbol, shares, cost, price, bought.isoformat()])
        if k in (3, 7, 12, 18):
            later = date(bought.year + 1, bought.month, bought.day)
            out.append([symbol, str(k), "%d.50" % (25 + 7 * k), price, later.isoformat()])
    return out


def main():
    typed = rows()
    positions = {}
    for symbol, shares, cost, price, bought in typed:
        p = positions.setdefault(symbol, {"lots": [], "price": cents(price)})
        p["lots"].append((Fraction(shares), cents(cost), date.fromisoformat(bought)))
    table, all_flows = [], []
    total_cost = total_value = 0
    for symbol, p in positions.items():
        shares = sum(s for s, _, _ in p["lots"])
        cost_exact = sum(s * c for s, c, _ in p["lots"])
        cost = half_up(cost_exact)
        value = half_up(shares * p["price"])
        flows = [(d, -half_up(s * c)) for s, c, d in p["lots"]]
        all_flows += flows
        dates_ = {d for _, _, d in p["lots"]}
        if len(dates_) == 1:
            days = (AS_OF - next(iter(dates_))).days
            annual = (Decimal(value) / Decimal(cost)) ** (Decimal(365) / Decimal(days)) - 1
        else:
            annual = xirr(flows + [(AS_OF, value)])
        table.append([symbol, int(shares * 10 ** 6), half_up(cost_exact / shares), cost, p["price"], value,
                      value - cost, half_up(Fraction(value - cost) * 10000 / cost), percent2(annual)])
        total_cost += cost
        total_value += value
    portfolio = xirr(all_flows + [(AS_OF, total_value)])
    values = sorted([(row[5], i, row[0]) for i, row in enumerate(table)], key=lambda t: (-t[0], t[1]))
    exact = [Fraction(v * 10000, total_value) for v, _, _ in values]
    floors = [int(e) for e in exact]
    for i in sorted(range(len(values)), key=lambda i: (-(exact[i] - floors[i]), i))[:10000 - sum(floors)]:
        floors[i] += 1
    data = {
        "as_of": AS_OF.isoformat(),
        "rows": typed,
        "expected": {
            "positions": table,
            "total_cost": total_cost,
            "total_value": total_value,
            "total_gain": total_value - total_cost,
            "total_gain_pct": half_up(Fraction(total_value - total_cost) * 10000 / total_cost),
            "portfolio_return_pct": percent2(portfolio),
            "allocation": [[s, v, w] for (v, _, s), w in zip(values, floors)],
        },
    }
    path = os.path.join(HERE, "vectors", "portfolio_20.json")
    with open(path, "w") as handle:
        json.dump(data, handle, indent=1)
        handle.write("\n")
    print("wrote", path, "-", len(typed), "rows,", len(table), "positions; portfolio return", float(portfolio))


if __name__ == "__main__":
    main()
