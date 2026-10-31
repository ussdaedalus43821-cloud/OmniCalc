# Escape hatches — calculators that run in Python instead of NovaLang

The default is that all calculation logic is NovaLang (`CLAUDE.md`, "Performance rule"). A
calculator moves to Python only when its UI path needs more than **100 ms (about 10k
interpreter steps)**. It then sits behind the same interface as the NovaLang version and has a
parity test against it.

## Entry format (every field required)

An entry missing any field is invalid. An escape hatch that isn't listed here is a bug.

```
### <calculator name>
- Python module:       src/<path>.py — the implementation that runs in the UI path
- Replaces interface:  src/<path>.nova :: <exported function(s)> — the NovaLang version it stands in for
- Parity test:         tests/<path> — runs both on the same inputs and requires identical results
- Reason:              measured cost of the NovaLang version (steps or ms, with inputs)
- Date added:          YYYY-MM-DD
```

## Entries

_None built._

## Planned escape hatches (not built)

Each is tracked here so it isn't forgotten. None is built yet, and none has a parity test.

### Multi-sign-change IRR over 60 periods
- **Python module:** `src/host/irr_scan.py` (planned).
- **Replaces interface:** `src/finance/cashflow.nova :: irr` (and so `irr_min_nonneg`), only
  for flows with **two or more sign changes and more than 60 periods**.
- **Parity test:** `tests/host/irr_scan_parity_test.py` (planned). It would run both on flows
  of 60 periods or fewer and require identical roots.
- **Reason:** the NovaLang Budan search costs O(K²) per root count. Measured: 120 ms at 30
  periods and 271 ms at 60. It refuses more than 60 periods, with an error that points here.
  Real cases (options, private equity, irregular working capital) are rare.
- **Status:** not built. **Target: M7 or later.** Moved from M6 because neither debt payoff nor any current screen needs it.
- **Date added:** 2026-10-31.

### XIRR with more than one sign change
- **Python module:** `src/host/xirr_scan.py` (planned).
- **Replaces interface:** `src/finance/cashflow.nova :: xirr`, for dated flows with two or
  more sign changes. `xirr` throws for these today, with an error that points here.
- **Parity test:** `tests/host/xirr_scan_parity_test.py` (planned). Single-sign-change flows
  through both must give the same rate within 1e-11.
- **Reason:** Budan's theorem needs a polynomial of manageable degree. With dated flows the
  exponents are day counts, so the degree is the number of days (thousands). A 5 bp grid of
  float XNPV evaluations would cost seconds in NovaLang.
- **Status:** not built. **Target: M7 or later.** Moved from M6 because neither debt payoff nor any current screen needs it.
- **Date added:** 2026-10-31.

## Decisions to keep in NovaLang (no escape hatch)

These were checked against the budget and stay in NovaLang. Re-measure if inputs grow.

### TVM rate solve — `src/finance/tvm.nova :: rate` (M1, 2026-10-31)
- Measured: 10 solves each, Python 3.13, direct interpreter (not `--bootstrap`). Re-measured in
  M2: the M1 figures came from loops written as `for i = 0 to 10`, and NovaLang's `to` is
  inclusive, so those loops ran 11 times and overstated each solve by about 10%.

  | Case | Per solve |
  |---|---|
  | 360 periods @ 6.5% | 5.4 ms |
  | 480 @ 24% | 7.4 ms |
  | 1,200 @ 3% | 14.4 ms |
  | 12 @ 0.5% | 3.0 ms |

  For comparison, `pmt` takes about 0.6–0.9 ms per call.
- Why it's fast: bisection takes about 40–50 iterations. Each iteration is two exact
  `pow()` calls on Python ints, so the step count stays low even though the ints have
  thousands of digits.
- Precision: exact rational residual. The result is within 1e-12 per period, and it is
  checked by re-deriving pmt/fv to within one minor unit.
- Decision: well under the 100 ms budget, with no precision gain from moving it to
  Python. It stays in NovaLang.

### Amortization schedule — `src/finance/amortization.nova` (M2, 2026-10-31)
- Measured: 10 schedules each, same setup as above.

  | Case | Per schedule |
  |---|---|
  | 360 monthly rows | 33.5 ms |
  | 628 biweekly rows | 54.9 ms |
  | 780 rows (the biweekly maximum for a 30-year term) | 57.5 ms |

- How it stays fast: the loop works on plain ints. It uses `money.round_half_up_whole`, the
  unchecked form of the one rounding rule, because the checks in `round_half_up` alone cost
  about 53 ms over 628 rows.
- Decision: within the 100 ms budget, so it stays in NovaLang. Re-measure before adding
  longer schedules (e.g. weekly) or per-row features, because cost grows linearly with rows.

### Unchecked core for schedule IRR — `cashflow.schedule_irr` (pre-M4, 2026-10-31)
- Before: per-flow validation cost about 37 ms of the 64 ms IRR on 361 flows, re-checking
  amounts that `amortization.nova` had already validated.
- After: `schedule_irr(schedule)` builds the flows straight from the schedule rows and
  calls the unchecked core (`shape_whole`). The checked `irr(from_schedule(...))` path is
  unchanged, and a test checks that the two agree.
- Measured end to end (pmt + schedule + IRR) in NovaLang: **89 ms → 60 ms**, under the 70 ms
  target.
- This is the second site of the unchecked-core pattern (the first is `money.round_half_up`).

### XIRR — `src/finance/cashflow.nova :: xirr` (M4, 2026-10-31)
- Measured: a 20-flow XIRR (one sign change) takes **26.5 ms**. Microsoft's 5-flow example
  takes 8.8 ms. It stays in NovaLang.

### Amortization screen, end to end through the host (M4, 2026-10-31)
- What's measured: `app.calculate` (NovaLang parse + pmt + schedule + schedule IRR + rows,
  through the embedding bridge).
- Headless, best of 3: about 52 ms on Python 3.13 and 55 ms on 3.12.
- GUI (Python 3.12, Tk 8.6, Xvfb), 16 Calculate presses, timed including drawing the 360-row
  table:
  - median **about 64 ms**, and 14 of 16 under 80 ms;
  - two spikes of 98 ms and **111 ms**, the same machine noise headless runs show.
- The first press in a fresh process ran 108 ms cold. `app.warm_up()` now runs one
  calculation at startup, so presses are always warm.
- Decision: stays in NovaLang. If spikes matter on slow machines, the next lever is the
  unchecked core again: the amortization row dicts and the façade's row re-pack. The other
  lever is fewer bisection steps in `schedule_irr`, e.g. a Newton start. Measure first.

### NPV / IRR — `src/finance/cashflow.nova` (M3, 2026-10-31)
- Measured: 10 calls each, same setup as above.

  | Case | Per call |
  |---|---|
  | **360-row mortgage: `from_schedule` + `irr_min_positive`** | **64.3 ms** |
  | Same, with 105.34 extra/month and two 10,000 lump sums | 62.4 ms |
  | Schedule + `from_schedule` + IRR, end to end | 88.7 ms |
  | Multiple sign changes, 2 periods (two roots) | 14.8 ms |
  | Multiple sign changes, 10 periods | 19.8 ms |
  | Multiple sign changes, 20 periods | 85.4 ms |
  | Multiple sign changes, 30 periods | **120.2 ms** (over budget) |
  | Multiple sign changes, 60 periods (the cap) | **271.3 ms** (over budget) |

- What was tried first: a plain 5 bp grid, one exact evaluation per cell, which is the brief's
  suggestion. It took 540 ms even for 2 periods. Replacing it with Budan isolation over the same
  grid cut that case to 15 ms (CLAUDE.md "IRR scan strategy").
- **Decision: stays in NovaLang, with two open items for review.**
  1. Multi-sign-change flows over about 25 periods exceed 100 ms (120 ms at 30 periods). The
     search refuses more than 60 periods, so the worst case is about 0.3 s. If longer
     multi-sign-change flows matter, the fix is a Python escape hatch for
     `cashflow.irr`'s V ≥ 2 path, with a parity test. That's best built with the M4 host, which
     brings the embedding a parity test needs.
  2. The end-to-end mortgage path (88.7 ms) leaves little headroom. If it grows, the first tool
     is the unchecked-core pattern: per-flow validation in `normalize` and `from_schedule` repeats
     checks the schedule already did.

### Pre-M5 optimizations — `schedule_table` + `table_irr` (2026-10-31)
- Amortization screen `calculate` in NovaLang: **56.7 → 40.5 ms**.
  - `schedule_table` (the int-row core) takes the schedule from 25.8 to 19.7 ms by skipping 2,880
    money dicts per call.
  - `table_irr` takes the IRR from 20.9 to 12.4 ms. It builds coefficients straight from the
    rows and starts from a 3-micro-unit bracket around the loan rate, so about 22 bisection
    steps instead of 32.

### M5 screens: calculate-path medians (2026-10-31)
- Measured headless through the bridge (`tools/perf.py`, 20 runs after a warm-up), and in the GUI
  (Python 3.12 + Tk under Xvfb, 20 presses each, including drawing the table):

  | Screen | Headless median / p90 | GUI median / p90 / max |
  |---|---|---|
  | Amortization | 43.0 / 57.4 ms | 50.9 / 72.6 / 88.2 ms |
  | Savings (30 yearly `tvm.fv` calls) | 14.9 / 15.5 ms | 19.5 / 21.1 / 25.7 ms |
  | **Refinance** (two schedules + break-even scan) | **54.8 / 58.4 ms** | **62.2 / 80.7 / 107.6 ms** |

- Every median is under the 70 ms M5 target, so no new unchecked core was needed. Refinance is the
  most expensive handler and the closest to the target. If it grows, the next lever is that
  `compare` only needs each schedule's payment column, not the full table.

### M6: refinance p90, debt payoff, and the CI baseline (2026-10-31)
- **Refinance p90**, GUI, 100 presses including drawing, four runs:

  | Run | p50 | p90 | p99 | max |
  |---|---|---|---|---|
  | 1 | 58.8 | 65.9 | 71.7 | 78.7 |
  | 2 | 60.1 | 70.7 | 107.3 | 108.7 |
  | 3 | 60.4 | 73.1 | 99.6 | 104.4 |
  | 4 | 61.0 | 69.7 | 102.0 | 130.5 |

  p90 is under the 80 ms threshold, so it's **not optimized**. The ~100+ ms outliers are p99-only
  noise. One 20-press run read p90 105, which shows 20 samples is too few for a p90. The suspected
  hotspot doesn't exist: `lifetime_savings` reuses the two schedules already built.
- **Debt payoff** (both strategies, 3 debts):
  - headless median 15.6 ms;
  - GUI p50/p90/p99 = 15.7 / 17.0 / 19.6 ms;
  - CI median 8.7 ms.
  Cost is about 45 µs per debt-month per strategy. The 10-debt, 166-month stress case is about
  70–80 ms per strategy, so the screen (which runs both) would be about 150 ms. That's over budget,
  but well beyond a household debt list. If it matters, the next lever is skipping paid-off debts
  in the inner loop.
- **CI baseline** (`tools/perf_baseline.json`, from run 41235056992): medians of 25.6 / 9.4 /
  37.2 / 8.7 ms for amortization / savings / refinance / debt payoff. CI runners are about 40%
  faster than this container.

### Debt payoff with 10+ debts — observed, not yet a problem (2026-10-31)
- **Observed:** about 45 µs per debt-month per strategy, and the screen runs both strategies. A
  10-debt, 166-month stress case is about 75 ms per strategy, so about 150 ms for the screen.
  Households with 3–6 debts take milliseconds.
- **Why not now:** 10+ debts is the edge, not the typical case. Comparing strategies is a
  deliberate press of Calculate, not a keystroke path.
- **Trigger:** if realistic usage exceeds **8 debts**, apply the unchecked-core pattern to
  `payoff_plan`'s inner loop. First, skip paid-off debts by keeping an open-index list. Re-measure
  before and after.

### The perf gate is calibrated (2026-10-31)
- On the PR #1 push, every screen ran 1.74–1.82× slower than in the baseline run, including debt
  payoff, whose code had not changed. That was the runner, not a regression. A raw-ms gate would
  have false-alarmed nightly.
- `tools/perf.py` now times a fixed NovaLang workload in the same process and gates on
  median ÷ calibration. The baseline is re-taken from CI run 41243936952.

### Investments screen — 20 positions, 24 lots (M7, 2026-10-31)
- Through the bridge, a 24-lot portfolio first took **136 ms**. The phases: parsing about 25 ms;
  positions about 45 ms, including four multi-lot XIRRs; portfolio XIRR about 28 ms; allocation
  about 8 ms.
- What was done:
  - the unchecked-core pattern twice: `position_summary_whole` for façade-built lots, and
    `allocation_of_values` so values aren't recomputed;
  - a regex shape check plus direct `num()` in `parse_helpers.date`;
  - Illinois instead of bisection inside XIRR's bracket;
  - XIRR's day exponents computed once per call.
- Result: **78–89 ms median** headless (best about 75–81 ms). That's inside the 100 ms budget
  but above the 70 ms target. In the GUI, the default 3-lot tab is 18 ms median.
- **After review:**
  - **Applied** a guessed-start XIRR (`cashflow.xirr_from_guess`). The guess is value ÷ cost
    annualized over first purchase → as-of, searched with a ±500 bp window and a full-search
    fallback; tests cover bad guesses of −50% and +900%. This brought the screen to
    **72–85 ms median** (`investments_20` in `tools/perf.py`), within the < 90 ms target for
    portfolio screens.
  - **Kept** the per-position XIRR for multi-lot positions. It answers "which position is my
    best performer?", so cutting it to hit a budget was the wrong lever.
- Tried and rejected: stopping Illinois once XNPV is under half a minor unit. It lost XIRR
  precision on small amounts, and the reference tests failed.

## NovaLang limitations found in M8 (math engine) — confirmed by probing v1.1.0

None of these needs an escape hatch: each is worked around in NovaLang. They're recorded so nobody
rediscovers them.

- **No `exp`, `asin`, `acos`, `atan` or hyperbolic built-ins.** Only `sin cos tan ln log10 sqrt
  pow` exist (`novalang.py` builtins). Workaround in `src/math/scientific.nova`:
  - `exp(x) = pow(E, x)`;
  - `atan` by argument reduction plus its Taylor series;
  - `asin`/`acos` from `atan`, and the hyperbolics from `exp`.
  Checked against Python's `math` module at a relative 1e-14.
- **`log` is the stderr logger, not a logarithm.** `log(8, 2)` *prints* "8 2" and returns
  nothing, so a mistaken call is silent. The evaluator's `log(x, base)` is our own function.
  NovaLang code must never call the built-in `log` for maths.
- **No exponent literals.** NovaLang source can't write `1e3`, and `num("1e3")` is rejected. The
  expression tokenizer reads exponents itself, exactly.
- **No float formatting control.** `str(float)` is Python's `repr`, and it prints large floats
  as all their binary digits: `str(pow(10.0, 25))` is `"10000000000000000905969664"`. Display is
  a routine of our own:
  - convert the float to its exact binary rational (doubling is exact);
  - round half-up to 12 significant figures with integer arithmetic.
  This matches Python's `Decimal(float)` digit for digit.
- **Precision ceiling:** transcendentals are binary doubles (about 15–17 significant digits),
  which is why the display uses 12.
- **`PI` and `E` don't exist inside imported modules** (found while implementing). They're
  globals of the top-level script only. A module function can call built-ins like `sqrt`, but
  `PI` is "undefined name". `scientific.nova` defines `MATH_PI = 3.141592653589793` and
  `MATH_E = 2.718281828459045`, verified bit-identical to the built-ins.
- **Evaluator cost** (measured after implementation; unchecked core not needed):
  - typical expressions take 2–4 ms;
  - `1000!` takes 3.4 ms and `2^4096` 1.2 ms;
  - cost grows about 0.06 ms per character, so a 479-character expression takes about 28 ms.
  The 500-character limit therefore bounds the worst case at roughly 30–40 ms, inside the 70 ms
  Math-tab target.

## Known approximations

Behavior that is deliberately not exact.

### CAGR uses a float power (M7)
- `investments.cagr` computes `(final / initial)^(1 / years)` with `pow()` on floats; a
  fractional power has no exact form.
- The result is returned as a rate `{num, den}` with 1e-12 precision, plus the float.
- It matches a 50-digit reference within 1e-10 (1e-12 for the RRI case) and Excel's RRI example
  to Excel's 7 shown digits.

### XNPV / XIRR discount factors are binary floats (M4)
- **What.** `cashflow.xnpv`/`xirr` discount each flow by `(1 + rate)^(days / 365)` using
  `pow()` on floats. Amounts stay integer minor units, and the sum is rounded half-up once.
- **Why.** That factor is irrational for almost every rate, so no exact form exists.
  Excel uses floats too. A fixed-point exp/ln series in NovaLang would cost about 1 s per XIRR.
- **Size.** The relative error is about 1e-15. XNPV matches a 50-digit decimal reference to
  the cent in every test, and XIRR matches it to 1e-11 (tests compare at 1e-11, not 1e-12).
- **Note.** Excel itself is less precise: its XIRR stops at 1e-8. Microsoft's example result
  0.373362535 is 1.5e-9 from the exact 0.37336253352. Each entry says what is approximated, why, and what to
use when exactness matters.

### `tvm.n` → `periods` slack (M1, documented in M2)
- **What.** `tvm.n` returns `{exact, periods}`. `periods` follows `tvm.whole_periods`: let
  `f = floor(exact)`; if `exact − f < 1e-4`, report `f`, otherwise `f + 1` (never below 1).
- **Why.** A target rounded to a minor unit pushes `exact` just past a whole number. The 120-month
  savings plan whose fv was rounded to the cent solves to `exact = 120.0000125`; plain
  `ceil()` would report 121 months.
- **What's approximate.** The honest answer is still 120.0000125. `periods = 120` is a
  display convenience, not a mathematical truth. **Financial logic must use `exact`**; no module
  may make decisions from `periods`.
- **Better alternative, deferred.** Snap only when the overshoot can be attributed to the
  rounding of fv/pv: compare the overshoot with the period fraction that one minor unit of the
  target is worth. It's more work and not needed yet.
- **Pinned by tests.** `tests/finance/tvm_test.nova` checks the boundary: 120.00005 → 120,
  120.0002 → 121.
