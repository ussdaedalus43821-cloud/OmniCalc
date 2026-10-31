#!/usr/bin/env python3
"""Reference vectors for tests/finance/tvm_test.nova.

Run `python3 tests/finance/gen_tvm_vectors.py` to regenerate. This script is an
independent implementation: Python's decimal module at 80 digits, using the
textbook closed forms (not the integerized forms in src/finance/tvm.nova),
and a 200-step decimal bisection for rates. Money values are in minor units,
rounded with ROUND_HALF_UP (halves away from zero), the same convention as
src/core/money.nova.

Convention (the same as tvm.nova): end-of-period payments, rate per period,
and the residual  pv*(1+r)^n + pmt*((1+r)^n - 1)/r + fv = 0.
"""

from decimal import ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 80
MICRO = Decimal(1000000)


def per_period(micro, periods):
    return Decimal(micro) / MICRO / Decimal(periods)


def half_up(value):
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def growth(r, n):
    return (1 + r) ** n


def annuity(r, n):
    return Decimal(n) if r == 0 else (growth(r, n) - 1) / r


def fv(pv, pmt, n, r):
    return -(pv * growth(r, n) + pmt * annuity(r, n))


def pv(fv_, pmt, n, r):
    return -(fv_ + pmt * annuity(r, n)) / growth(r, n)


def pmt(pv_, fv_, n, r):
    return -(pv_ * growth(r, n) + fv_) / annuity(r, n)


def n_periods(pv_, fv_, pmt_, r):
    if r == 0:
        return -(pv_ + fv_) / pmt_
    return ((pmt_ - fv_ * r) / (pmt_ + pv_ * r)).ln() / (1 + r).ln()


def residual(pv_, fv_, pmt_, n, r):
    return pv_ * growth(r, n) + pmt_ * annuity(r, n) + fv_


def solve_rate(pv_, fv_, pmt_, n, lo, hi):
    f_lo = residual(pv_, fv_, pmt_, n, lo)
    assert f_lo * residual(pv_, fv_, pmt_, n, hi) < 0, "bracket has no sign change"
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = residual(pv_, fv_, pmt_, n, mid)
        if (f_mid < 0) == (f_lo < 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def show(label, value):
    print("{:<44} {}".format(label, value))


def as_rate(value):
    """A per-period rate as the {num, den} tvm_test.nova compares against:
    value = num / (den * 1e6) with den = 1e24, i.e. num = round(value * 1e30)."""
    return "{{num: {}, den: {}}}".format(half_up(value * Decimal(10) ** 30), 10 ** 24)


def main():
    D = Decimal
    # 1. Canonical mortgage: 200,000.00 at 6.5%/12 for 360 periods, cents.
    r = per_period(65000, 12)
    m_pmt = half_up(pmt(D(20000000), D(0), 360, r))
    show("mortgage pmt (cents)", m_pmt)
    m_fv = half_up(fv(D(20000000), D(m_pmt), 360, r))
    show("mortgage fv with rounded pmt", m_fv)
    m_pv = half_up(pv(D(0), D(m_pmt), 360, r))
    show("mortgage pv with rounded pmt", m_pv)
    show("mortgage n with rounded pmt", n_periods(D(20000000), D(0), D(m_pmt), r))
    m_rate = solve_rate(D(20000000), D(0), D(m_pmt), 360, D("0.001"), D("0.01"))
    show("mortgage rate implied by rounded pmt", m_rate)
    show("  as {num, den}", as_rate(m_rate))
    show("  minus 0.065/12", m_rate - r)

    # 2. The same mortgage at scale 6 (micro-dollars): pmt rounding is small
    #    enough that the solved rate must land within 1e-9 of 0.065/12.
    m6_pmt = half_up(pmt(D(200000000000), D(0), 360, r))
    show("mortgage pmt (scale 6)", m6_pmt)
    m6_rate = solve_rate(D(200000000000), D(0), D(m6_pmt), 360, D("0.001"), D("0.01"))
    show("scale-6 rate as {num, den}", as_rate(m6_rate))
    show("scale-6 rate minus 0.065/12", m6_rate - r)

    # 3. Zero rate: 1,200.00 repaid over 12 periods.
    show("zero-rate pmt", half_up(pmt(D(120000), D(0), 12, D(0))))

    # 4. Negative rate: deposit 10,000.00 at -1%/12 for 12 periods, no payments.
    rn = per_period(-10000, 12)
    neg_fv = half_up(fv(D(-1000000), D(0), 12, rn))
    show("negative-rate fv", neg_fv)
    show("negative-rate pv from that fv", half_up(pv(D(neg_fv), D(0), 12, rn)))
    show("negative-rate n from that fv", n_periods(D(-1000000), D(neg_fv), D(0), rn))
    neg_rate = solve_rate(D(-1000000), D(neg_fv), D(0), 12, D("-0.002"), D("-0.0005"))
    show("negative-rate rate implied by rounded fv", neg_rate)
    show("  as {num, den}", as_rate(neg_rate))
    show("  minus -0.01/12", neg_rate - rn)

    # 5. Savings: 100.00 deposited at the end of each month, 5%/12, 120 periods.
    rs = per_period(50000, 12)
    s_fv = half_up(fv(D(0), D(-10000), 120, rs))
    show("savings fv", s_fv)
    show("savings n from that fv", n_periods(D(0), D(s_fv), D(-10000), rs))
    s_rate = solve_rate(D(0), D(s_fv), D(-10000), 120, D("0.001"), D("0.01"))
    show("savings rate implied by rounded fv", s_rate)
    show("  as {num, den}", as_rate(s_rate))


if __name__ == "__main__":
    main()
