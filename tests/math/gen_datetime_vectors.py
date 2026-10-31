#!/usr/bin/env python3
"""Reference vectors for src/math/datetime.nova (docs/M8-MATH-DESIGN.md).

Run `python3 tests/math/gen_datetime_vectors.py` to regenerate
tests/math/vectors/datetime.json. A separate implementation on Python's
datetime.date and fractions.Fraction - no code shared with the NovaLang side.

Conventions (as the design states them):
- add_duration(date, {years, months, days}): years*12 + months are added first, clamping
  the day to the target month's last day; then days. Negative values subtract.
- duration_between(a, b): the largest whole number of months m with
  add_months(a, m) <= b, then the remaining days; years = m // 12, months = m % 12.
  For a > b it is the reverse duration with every field negated.
- weekday: 0 = Monday ... 6 = Sunday.
- business days: Monday-Friday that are not in the holiday list.
  add_business_days(d, n): Excel WORKDAY - d itself is not counted; n = 0 returns d.
  business_days_between(a, b): business days in (a, b] (Excel NETWORKDAYS counts
  [a, b]); negative when a > b.
- day_count(start, end, convention) -> exact year fraction, start <= end:
  "act/365f"  actual days / 365
  "act/360"   actual days / 360
  "30/360"    ISDA 2006 4.16(f) bond basis: D1 = 30 if d1 = 31; D2 = 30 if d2 = 31 and D1 = 30
  "30e/360"   ISDA 2006 4.16(g) Eurobond: D1 = min(d1, 30), D2 = min(d2, 30)
  "act/act-isda"  days falling in leap years / 366 + days in other years / 365
"""

import calendar
import json
import os
from datetime import date, timedelta
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
EPOCH_ORDINAL = date(1970, 1, 1).toordinal()


def ymd(d):
    return [d.year, d.month, d.day]


def serial(d):
    return d.toordinal() - EPOCH_ORDINAL


def add_months(d, months):
    total = d.year * 12 + (d.month - 1) + months
    y, m = divmod(total, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def add_duration(d, years, months, days):
    return add_months(d, years * 12 + months) + timedelta(days=days)


def duration_between(a, b):
    if a > b:
        y, m, dd = duration_between(b, a)
        return [-y, -m, -dd]
    months = (b.year - a.year) * 12 + (b.month - a.month)
    while months > 0 and add_months(a, months) > b:
        months -= 1
    rest = (b - add_months(a, months)).days
    return [months // 12, months % 12, rest]


def is_business(d, holidays):
    return d.weekday() < 5 and d not in holidays


def add_business_days(d, n, holidays):
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining:
        d += timedelta(days=step)
        if is_business(d, holidays):
            remaining -= 1
    return d


def business_days_between(a, b, holidays):
    if a > b:
        return -business_days_between(b, a, holidays)
    count, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if is_business(d, holidays):
            count += 1
    return count


def day_count(start, end, convention):
    assert start <= end
    if convention == "act/365f":
        return F((end - start).days, 365)
    if convention == "act/360":
        return F((end - start).days, 360)
    if convention in ("30/360", "30e/360"):
        d1, d2 = start.day, end.day
        if convention == "30/360":
            if d1 == 31:
                d1 = 30
            if d2 == 31 and d1 == 30:
                d2 = 30
        else:
            d1, d2 = min(d1, 30), min(d2, 30)
        days = 360 * (end.year - start.year) + 30 * (end.month - start.month) + (d2 - d1)
        return F(days, 360)
    if convention == "act/act-isda":
        total = F(0)
        for year in range(start.year, end.year + 1):
            lo = max(start, date(year, 1, 1))
            hi = min(end, date(year + 1, 1, 1))
            if hi > lo:
                total += F((hi - lo).days, 366 if calendar.isleap(year) else 365)
        return total
    raise ValueError(convention)


US_2024 = [date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 5, 27), date(2024, 6, 19),
           date(2024, 7, 4), date(2024, 9, 2), date(2024, 10, 14), date(2024, 11, 11), date(2024, 11, 28),
           date(2024, 12, 25)]


def main():
    D = date
    cases = {"weekday": [], "add_duration": [], "duration_between": [], "is_business_day": [],
             "add_business_days": [], "business_days_between": [], "day_count": []}
    for d in [D(1970, 1, 1), D(2024, 2, 29), D(2026, 10, 31), D(2000, 1, 1), D(1969, 12, 31)]:
        cases["weekday"].append({"date": ymd(d), "weekday": d.weekday()})
    for d, y, m, dd, note in [
        (D(2024, 1, 31), 0, 1, 0, "clamps to Feb 29 in a leap year"),
        (D(2023, 1, 31), 0, 1, 0, "clamps to Feb 28"),
        (D(2024, 2, 29), 1, 0, 0, "a leap day plus a year clamps to Feb 28"),
        (D(2024, 3, 31), 0, -1, 0, "minus a month clamps to Feb 29"),
        (D(2024, 1, 31), 0, 1, 1, "months first, then days: Feb 29 + 1 = Mar 1"),
        (D(2024, 1, 15), 1, 2, 10, "combined"),
        (D(2024, 3, 1), 0, 0, -1, "minus a day crosses into a leap February"),
        (D(2024, 12, 31), 0, 0, 1, "crosses a year"),
        (D(2024, 5, 31), -2, -3, -40, "all negative"),
    ]:
        cases["add_duration"].append({"date": ymd(d), "years": y, "months": m, "days": dd,
                                      "result": ymd(add_duration(d, y, m, dd)), "note": note})
    for a, b, note in [
        (D(2024, 1, 31), D(2024, 2, 29), "exactly one month (clamped)"),
        (D(2024, 1, 31), D(2024, 3, 1), "one month and one day"),
        (D(2020, 2, 29), D(2024, 2, 28), "leap day to the day before"),
        (D(2023, 5, 15), D(2026, 10, 31), "years, months and days"),
        (D(2024, 6, 10), D(2024, 6, 10), "same day"),
        (D(2026, 10, 31), D(2023, 5, 15), "reversed: every field negated"),
    ]:
        cases["duration_between"].append({"a": ymd(a), "b": ymd(b), "result": duration_between(a, b), "note": note})
    holidays = set(US_2024)
    for d, note in [(D(2024, 7, 4), "a holiday"), (D(2024, 7, 6), "a Saturday"), (D(2024, 7, 8), "a Monday"),
                    (D(2024, 7, 7), "a Sunday")]:
        cases["is_business_day"].append({"date": ymd(d), "result": is_business(d, holidays), "note": note})
    for d, n, note in [
        (D(2024, 12, 20), 3, "Fri + 3 skips the weekend and Dec 25"),
        (D(2024, 7, 5), -1, "back over the Jul 4 holiday"),
        (D(2024, 7, 6), 0, "n = 0 returns the date itself, even a Saturday (Excel WORKDAY)"),
        (D(2024, 7, 6), 1, "from a Saturday, the next business day"),
        (D(2024, 1, 1), 250, "250 business days into 2024"),
        (D(2024, 11, 29), -20, "20 back across Thanksgiving and Veterans Day"),
    ]:
        cases["add_business_days"].append({"date": ymd(d), "n": n, "result": ymd(add_business_days(d, n, holidays)),
                                           "note": note})
    for a, b, note in [
        (D(2024, 1, 1), D(2024, 12, 31), "all of 2024: 262 weekdays - 11 holidays"),
        (D(2024, 7, 3), D(2024, 7, 8), "(Wed, Mon]: Thu is a holiday"),
        (D(2024, 7, 8), D(2024, 7, 8), "empty interval"),
        (D(2024, 7, 8), D(2024, 7, 3), "reversed: negative"),
    ]:
        cases["business_days_between"].append({"a": ymd(a), "b": ymd(b),
                                               "result": business_days_between(a, b, holidays), "note": note})
    for a, b in [(D(2023, 1, 31), D(2023, 3, 31)), (D(2024, 2, 29), D(2024, 8, 31)), (D(2023, 12, 15), D(2025, 1, 15)),
                 (D(2024, 1, 31), D(2024, 2, 29)), (D(2020, 2, 29), D(2021, 2, 28)), (D(2024, 6, 30), D(2024, 12, 31))]:
        for convention in ["act/365f", "act/360", "30/360", "30e/360", "act/act-isda"]:
            f = day_count(a, b, convention)
            cases["day_count"].append({"a": ymd(a), "b": ymd(b), "convention": convention,
                                       "num": f.numerator, "den": f.denominator})
    data = {"holidays": [ymd(h) for h in US_2024], "cases": cases}
    os.makedirs(os.path.join(HERE, "vectors"), exist_ok=True)
    with open(os.path.join(HERE, "vectors", "datetime.json"), "w") as handle:
        json.dump(data, handle, indent=1)
        handle.write("\n")
    print("datetime.json:", {k: len(v) for k, v in cases.items()})
    print("2024 (Jan 1, Dec 31] business days with US holidays:", cases["business_days_between"][0]["result"])
    for c in cases["day_count"][:10]:
        print("  ", c["a"], c["b"], c["convention"], "%d/%d" % (c["num"], c["den"]))


if __name__ == "__main__":
    main()
