# OmniCalc — Claude Code Rules

## Project
OmniCalc is a modular calculator: math engine + finance engine + UI + local storage + export.
v1 is a **Python-hosted desktop app with a Tkinter UI**. Web/mobile are out of scope.
The decision record is in `docs/NOVALANG-QUESTIONS.md` ("Decisions 2026-10-31").

## NovaLang rules
- NovaLang version: **v1.1.0**, pinned as a git submodule at `vendor/Nova_Lang` (commit `02eabdb`).
  At startup the host asserts that the interpreter version is `"1.1.0"` (`novalang.py:74`).
  Never patch the submodule; report upstream issues instead.
- Runtime/compiler: the `novalang.py` tree-walking interpreter on CPython 3.7+. There is no compiler
  (`Nova_Lang/README.md` "Quick start", "Self-hosting"). The host embeds it through the `Nova` class
  (`README.md` "Embedding NovaLang in Python").
- Build command: **none.** NovaLang has no build step.
- Test command: `python3 tools/run_tests.py` (runs the pin check, then every `tests/**/*.nova`).
  Nightly CI only: `python3 tools/run_tests.py --bootstrap` (about 50x slower; the dates test
  takes about 50 s).
- Formatter/linter: **none exists** (`novalang.py:4154`, `--bootstrap` is the only flag).
  Follow `Nova_Lang/CONTRIBUTING.md` "Style" by hand.
- Do NOT invent NovaLang syntax or stdlib. Cite docs/examples. Known gaps and traps:
  - There is no `**` operator (use `pow()`), no bitwise ops, and no `null` literal.
  - `round()` is float half-even; never use it for money.
  - `/` returns a float when the division is inexact (`novalang.py:3258-3265`). Integer code uses
    only `+ - * // %`; `//` floors (`novalang.py:3266-3269`).
  - `type()` reports `"number"` for both ints and floats. Floats can be NaN or inf (`num()` of a
    long decimal string returns `inf`, and `json.loads("NaN")` returns `nan`), and `floor()` on
    either **crashes the interpreter** with a raw Python error. All whole-number checks go
    through `src/core/numbers.nova` (`is_finite`, `is_whole`, `require_whole`), which rejects
    non-finite values before calling `floor()`.
  - Built-in names (`min`, `max`, `sum`, `num`, `values`, `keys`, `copy`, `remove`, `set`,
    `get`, ...) and keywords (`to`, `step`, `in`, `with`, `as`, `delete`) can't be used as
    variable, parameter or function names.
  - There is no hoisting at top level: a function must be defined before top-level code calls
    it. Calls from inside function bodies can go to functions defined later.
  - **`for i = a to b` is INCLUSIVE of `b`** (verified; `Nova_Lang/README.md` wrongly says
    "counts 0..9" for `0 to 10`). `range(n)` is exclusive. To visit `n` items, write
    `for i = 0 to n - 1` or `for i = 1 to n`.
- If NovaLang cannot express a platform feature, isolate that feature behind a thin adapter and document it.
- Prefer NovaLang for domain logic: math, finance, validation, and numeric formatting decisions
  (scale, rounding). The host turns the result into display strings.
- Use host-platform glue only when NovaLang has no supported path.

## Money contract (the formatting boundary)
- Every NovaLang money value is `{minor: <int>, scale: <int>, currency: "<code>"}`, built and
  checked by `src/core/money.nova`. For example, `{minor: 1999, scale: 2, currency: "USD"}` is
  19.99 USD.
- The host's **only** formatting job is `minor` + `scale` + `currency` → display string. It
  never rounds, scales, converts, or does arithmetic on money. Any rounding the display needs
  is done in NovaLang first.

## Host / NovaLang boundary
| Python host owns | NovaLang owns |
|---|---|
| Tkinter UI, file I/O, process launch | All calculation logic |
| CSV writing (`csv` module) from integer rows + scale | Producing those rows |
| Date string parsing/formatting, "today" → `{y, m, d, serial}` | All date math on serial day numbers |
| Rendering integers + scale as display strings | Money, rates, rounding, solvers, schedules |

## Number rules
- **Money** is integer minor units with an explicit currency scale, end to end. Never binary floats.
  No Python `decimal`.
- **Rates** are integer micro-units of a fraction (1e-6): 6.5% = `65000`. A periodic rate is
  annual / periods with the remainder carried, never pre-rounded.
- **Rounding** is half-up (halves away from zero), and only at cash-flow boundaries (each
  amortization period) and at display. Never round intermediate arithmetic.
- **Two rate-multiplication primitives** (`src/core/money.nova`):
  - `multiply_rate_exact(a, rate)` returns `{num, den, scale, currency}`, meaning `num / den`
    minor units, unrounded.
  - `multiply_rate(a, rate)` is that same value rounded half-up once. Use it for **one cash
    flow**, never inside a solver.
- **The one rounding rule** is written once, in `money.round_half_up_whole(n, d)`.
  `money.round_half_up` validates its inputs and then delegates to it. Use the unchecked
  `_whole` form only in hot loops whose operands are ints already validated upstream
  (amortization). Anywhere else, use the checked form.

## Hot-loop primitives: unchecked core + checked wrapper
- A primitive that runs inside a hot loop comes in two forms:
  - a **checked public wrapper** that validates its inputs and then delegates;
  - an **unchecked core** (suffix `_whole`, or another name stated in its comment) that holds
    the arithmetic and assumes valid inputs.
- **The checked wrapper carries the validation tests. The unchecked core carries the arithmetic
  tests,** including a test that both forms agree. The core may only be called from code that
  has already validated those exact operands.
- When a module approaches the 100 ms budget, reach for this pattern **before** an escape hatch.
- Primitives in this pattern:
  - `money.round_half_up` (checked) / `money.round_half_up_whole` (unchecked core, used by
    `amortization.nova`).

## Solver rules
- **Sign convention.** Cash received is positive and cash paid out is negative. A loan you take
  out has `pv > 0` and `pmt < 0`; a savings plan has `pmt < 0` and `fv > 0`.
- **Period convention.** Payments fall at the end of each period. `rate` is always the rate
  **per period**; converting from annual is the caller's job (`rates.per_period(rates.annual(m),
  12)`). `n` is a whole number of periods.
- **Residuals are never evaluated in rounded minor units.** Rounding would make them
  step functions of the rate. Solvers use exact rational arithmetic instead:
  - `multiply_rate_exact` for single-period products;
  - integer compounding factors `A = (D + num)^n`, `B = D^n`, where `pow()` on ints is exact;
  - floats only where exact rationals are impractical, i.e. the logarithms in `n`.
  Only the final answer is rounded.
- **`tvm.fv` / `pv` / `pmt`:** exact closed forms, rounded half-up once, to a minor unit.
- **`tvm.n`:** closed form through logarithms, in floats. At a zero rate it's `-(pv + fv) / pmt`.
  - Returns `{exact, periods}`. `exact` is the real-valued solution and is not rounded.
    `periods` follows `tvm.whole_periods`: let `f = floor(exact)`; if `exact − f < 1e-4`,
    report `f`, otherwise `f + 1`, and never below 1.
  - **`periods` is a UI convenience, not a mathematical truth.** Financial logic must use
    `exact`; no module may base decisions on `periods`. This is listed as a known approximation
    in `docs/ESCAPE-HATCHES.md`.
  - No summation fallback: when the closed form has no positive solution, no `n` exists, and
    `n` throws.
- **`tvm.rate`:** bisection on the exact residual's sign.
  - Bracket: walk outward from 0 and stop at the first sign change. Upward the candidates are
    0.1%/period doubling to about 1,048,576%; downward they're -0.1% doubling to -51.2%, then
    -75%, -90%, -99%, -99.9%, -99.99%. The positive side is tried first.
  - **Multiple roots.** The **smallest positive root** is returned, matching Excel's RATE. A
    test pins this: −100, +230, −132 has roots 10% and 20%, and `rate` must return 10%.
    Known limit: two roots between the same pair of neighbouring candidates are missed. IRR
    (M3) needs a finer scan.
  - Bisection runs over a power-of-two denominator and stops at a width of 1e-12 per period,
    capped at 200 iterations (a real case takes about 40–50).
  - The answer is returned as an exact `{num, den}` and is **not** rounded to a micro-unit;
    rounding happens only at display.
  - Before returning, the answer is verified at minor-unit precision: recomputing `pmt` (or
    `fv` when `pmt` is 0) must reproduce the input within one minor unit, or `rate` throws.
- **What round-trip tests can promise.** Once a value has been rounded to a minor unit, rebuilding
  the inputs from it is only exact up to that rounding. For example, pv rebuilt from the
  cent-rounded mortgage payment is 200,000.63, and the cent payment implies a rate 2.5e-8
  per period off 6.5%/12. Tests therefore check two things:
  - re-solving from a rebuilt value gives the same rounded value;
  - precision targets like "within 1e-9" are met at a scale fine enough for them (scale 6).
- **Dates**: add-months with end-of-month clamping, 30/360, actual/365, actual/actual, and
  schedule generation all live in NovaLang.

## IRR scan strategy (`src/finance/cashflow.nova`) — written before coding, revised after measuring (M3)
- **Measured first.** The brief's blind 5 bp grid over [−99%, +100%] is 3,981 exact residual
  evaluations:
  - **540 ms even for a 2-period flow**;
  - for a 360-period flow, plain Horner costs 4.1 ms per evaluation, so about 16 s for the grid.
  A cell-by-cell grid can't meet the 100 ms budget.
- **The domain.** NPV is the polynomial `P(x) = Σ c_j x^j` in `x = 1/(1+r)`, whose coefficients
  are the flows in period order.
- **Descartes' rule of signs.** With `V` sign changes among the non-zero flows, the number of
  roots with r > −100% is at most `V` and has the same parity as `V`.
- **`V = 0`:** no root. `irr` returns `[]` without searching.
- **`V = 1`:** exactly one root, so the search is fast and complete.
  - Bracket by walking outward from 0 with `tvm.rate`'s candidate lists
    (−99.99% … 1,048,576%), then bisect exactly.
  - This covers every conventional loan and investment, including `from_schedule`.
- **`V ≥ 2`: the same 5 bp grid over [−99%, +100%), searched by Budan's theorem** instead of
  cell by cell.
  - The number of roots in `(a, b]` is at most `V(a) − V(b)`, with the same parity, where
    `V(c)` counts sign changes in the coefficients of `P(x + c)`. A grid point
    `x_i = 2000 / (2000 + i)` is shifted in exactly with integer Horner.
  - Split the grid-index range recursively, keeping each piece whose bound is ≥ 1:
    - a bound of 0 means no root, so skip the piece;
    - a bound of 1 means one root, so bisect it exactly;
    - a single 5 bp cell bisects whatever sign change it shows.
    Bounds are memoized per grid point.
  - **Guarantee:** every root that's alone in its 5 bp cell is found, so any two roots at least
    10 bp apart are always both found. A test pins 10% and 10.1%.
  - **Not found:** roots outside [−99%, +100%), an even number of roots in one cell, and
    double roots.
  - **Cost bound:** `O(K²)` integer steps per Budan count, with about 2 × log₂(3,980) ≈ 25
    counts for two roots. Measured: 15 ms at 2 periods, 85 ms at 20, 120 ms at 30.
  - **Hard cap:** V ≥ 2 flows over **60 periods** (about 270 ms) are refused with an error.
    Over-budget cases are listed in `docs/ESCAPE-HATCHES.md`.
- **Exact evaluation.**
  - With `r = num / D`, `D = den × MICRO`, `G = D + num`: `NPV = N / G^K` where
    `N = Σ c_j · D^j · G^(K−j)`, and `G^K > 0`.
  - **Runs of equal consecutive flows are compressed** into one closed-form term,
    `c · D^a · G^(K−b) · (G^m − D^m) / (G − D)` with `m = b − a + 1` (and `m · D^K` when
    `G = D`). The division is exact. A 360-row schedule is about 3 runs.
- **Bisection and verification.** The pattern is `tvm.rate`'s (power-of-two denominators, at
  most 200 steps), but it stops only when **both** the width is ≤ 1e-12 per period **and** the NPV
  at the midpoint is within one minor unit of 0. At scale 6, a 360-period schedule needs about
  1e-14. Roots are `{num, den}` per period, sorted ascending, and not rounded.
- **No shared root-finder yet.** `cashflow.nova` copies `tvm.rate`'s candidates and bisection.
  Extract a shared one when a third user appears.
- **What schedule round-trips can promise.** A cent schedule's IRR is **not** exactly its loan
  rate: per-period interest rounding moves it by 1.19e-9 (−3.68 cents over 360 rows). The test
  therefore checks two things:
  - at cents, the IRR against the exact reference within 1e-12;
  - at scale 6, the IRR back to the loan rate within 1e-9.

## Amortization rules (`src/finance/amortization.nova`)
- **Magnitudes, not signed cash flows.** Principal, payment, extra and lump sums are positive
  money, and rows report positive amounts. To use a TVM payment, which is negative, pass
  `money.negate(tvm.pmt(...))`.
- **A schedule is for display, not cash-flow analysis.** For NPV or IRR, convert it with
  `cashflow.from_schedule(schedule)`: principal `+` at period 0, each row's payment `−`, from the
  borrower's view. It is the **only** place a schedule's signs flip, and it is tested end to end
  against IRR.
- **Rate per period**, exactly as supplied. The same rule as TVM.
- **Each period:** `interest = balance × rate`, rounded half-up once; then
  `scheduled = regular + extra + lump`.
- **Final-payment convention.** If `scheduled ≥ balance + interest`, or it's period `n`, that
  row is the **final** row (`kind: "final"`). It pays exactly `balance + interest`, and the
  difference is recorded in that row:
  - `adjustment = paid − scheduled`. It is negative when the payment was adjusted down (a
    rounded-up payment, or an early payoff) and positive when adjusted up (a rounded-down
    payment falling short).
  - It is never silently absorbed.
  - Every row satisfies `payment == regular + extra + adjustment == interest + principal`.
- **Biweekly** means 26 periods a year, each paying **half the monthly payment** (rounded
  half-up), at the **rate per biweekly period the caller supplies** (normally
  `rates.per_period(rates.annual(m), 26)`). It is never re-derived from a monthly rate. The cap
  is `ceil(n_months × 26 / 12)` periods. At 6.5% a 30-year loan pays off in 628 periods
  (24.15 years).
- **Rejected loudly**, and each case has a test:
  - principal ≤ 0, payment ≤ 0, extra < 0, n < 1, or mixed currencies;
  - a lump sum that isn't positive, falls outside 1..n, or is malformed;
  - **negative amortization**: payment + extra that doesn't exceed the first period's
    interest.

## Performance rule
- UI-path budget: **100 ms**, roughly 10k interpreter steps (interpreter speed is about 162k
  steps/s, `Nova_Lang/README.md` "ECS & particle engine").
- A calculator over budget (e.g. Monte Carlo, large IRR searches, bulk jobs) moves to Python behind
  the same interface. It must have a **parity test** against the NovaLang version and be listed in
  `docs/ESCAPE-HATCHES.md`.
- Every `docs/ESCAPE-HATCHES.md` entry must name all of: the **Python module**, the **NovaLang
  interface** it replaces (file + exported functions), and the **parity test file**. An entry
  missing any of these is invalid. An unlisted escape hatch is a bug.

## Testing rules
- Tests are `tests/**/*.nova`. Every `.nova` file under `tests/` is a test; shared helpers live
  in `tools/`.
- Tests import `tools/check.nova` (`check`, `check_true`, `check_throws`) and end with
  `t.finish()`. `finish()` prints the sentinel `TESTS_OK <n>` only when every check passed;
  otherwise it prints the failures and exits 1. The count is printed with `str()`, never
  `len()`.
- Every test file starts with a header comment block containing both of:
  ```
  # module: money
  # expect: 31
  ```
  `module` must name exactly one `src/**/<module>.nova`. `expect` is the exact number of checks
  the file runs. Both may share one line.
- **Fail closed.** `tools/run_tests.py` fails a file on any of:
  - a missing, duplicate or malformed `module` or `expect` header;
  - a module name that doesn't resolve to exactly one file;
  - a non-zero exit or a timeout;
  - anything other than exactly one `TESTS_OK <n>`, as the last line of output;
  - `n` ≠ `expect`.
  Finding no test files at all is also a failure. Nothing is skipped.
- The runner first calls `src/host/nova_runtime.assert_pinned()`. It checks that the
  interpreter reports `__version__ == "1.1.0"` and that the submodule HEAD is `02eabdb...`.
- Tests run on every change. `--bootstrap` is a separate nightly CI job, not a gate.
- All core finance math must have deterministic golden tests with known values (`tests/finance`).

## Engineering rules
- Every finance calculator must support “solve for any variable.”
- Every loan calculator must generate an amortization schedule.
- Every result screen must show formula/assumptions and allow CSV export.
- No ads, no tracking, offline-first.
- Do not build the whole app at once. Work milestone by milestone and stop for review after each one.

## v1 scope
Scientific, units, TVM, amortization, compound interest, amortization CSV export. **No tax.**
(`business`, the rest of `investments`, storage and PDF are post-v1 unless re-scoped.)

## Architecture
- vendor/Nova_Lang — pinned submodule (read-only)
- src/host/nova_runtime.py — loads the pinned interpreter, startup version + commit assertion
- src/core/numbers.nova, money.nova, rates.nova, dates.nova — foundation (M0, numbers.nova in M1)
- src/core/math — scientific, units, algebra hooks
- src/finance/tvm.nova — PV/FV/PMT/N/rate (M1)
- src/finance/cashflow.nova — NPV, IRR, payback, from_schedule (M3)
- src/finance/amortization.nova — schedules, extra payments, biweekly (M2); refinance later
- src/finance/investments — compound interest (v1); CAGR, DCA, retirement (later)
- src/finance/business — margin, break-even, ROI, depreciation (post-v1)
- src/ui — Tkinter calculator screens (host)
- src/storage — presets, scenarios, local DB (post-v1)
- src/export — CSV (v1, host); PDF (post-v1)
- tools/run_tests.py — test runner; tools/check.nova — check() helper and sentinel
- tests/core, tests/finance — golden test vectors

## Milestones
- **M0 — Foundation only. No calculator modules.** ✅ done, reviewed
  - Add the submodule at `02eabdb` and the version assertion.
  - `money.nova` (API surface only):
    - `make`, `add`, `subtract`, `negate`, `multiply_int`, `multiply_rate`, `compare`;
    - `round_half_up`, which rounds halves away from zero.
  - `rates.nova` (API surface only):
    - `annual(micro)`, `per_period` (the remainder is carried as an exact `{num, den}`);
    - `micro_whole`, `micro_remainder`, `check_rate`. Nothing here rounds.
  - `dates.nova` (API surface only):
    - `from_civil`, `from_serial`, `check_date`, `add_days`, `days_between`;
    - `add_months` (clamps to month-end, and the clamp doesn't stick);
    - `day_count_actual_365`, plus the helpers `is_leap_year` and `days_in_month`.
  - Other day-count conventions (30/360, actual/actual) land with the module that needs them.
  - `tools/run_tests.py` with the sentinel and count check, plus tests for all three modules.
- **M1 — TVM only.** ✅ done, reviewed.
  - `src/finance/tvm.nova`: `fv`, `pv`, `pmt`, `n`, `rate`.
  - `money.multiply_rate_exact` split, and `src/core/numbers.nova` (the NaN/Inf guard).
  - Tests: `tests/finance/tvm_test.nova`, with Python reference vectors from
    `tests/finance/gen_tvm_vectors.py`.
  - CI: `.github/workflows/tests.yml`.
  - NPV/IRR are deferred to M3.
- **M2 — Amortization schedules only.** ✅ done, reviewed.
  - `src/finance/amortization.nova`: `schedule`, `schedule_with_extra`, `schedule_biweekly`.
  - Tests: `tests/finance/amortization_test.nova`, with Python vectors from
    `tests/finance/gen_amortization_vectors.py` and a row-by-row diff against
    `tests/finance/vectors/mortgage_200k_6_5_360.json`.
  - Not in M2: refinance, rent-vs-buy, extra-payment comparison logic.
- **M3 — NPV/IRR and uneven cash flows.** 🚧 in progress, awaiting review.
  - `src/finance/cashflow.nova`: `npv`, `irr` (all roots found), `irr_min_positive`, `payback`
    (undiscounted, linearly interpolated), and `from_schedule`.
  - Tests: `tests/finance/cashflow_test.nova`, with Python vectors from
    `tests/finance/gen_cashflow_vectors.py`.
  - Not in M3: XNPV/XIRR, which need dated flows.
- **M4 — XNPV/XIRR, dates-based cash flows, and the start of the UI host.**
- **Later — compound interest** (`investments`).
- **Later — Scientific + units** (`core/math`).
- **Later — the full Tkinter host:** screens with formula/assumptions, CSV export, a terminal debug
  harness.
- **CI** (`.github/workflows/tests.yml`): `tools/run_tests.py` on every push and PR, plus a nightly
  `--bootstrap` job (cron, 07:17 UTC).
