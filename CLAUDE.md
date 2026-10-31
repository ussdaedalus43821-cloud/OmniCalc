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

## Amortization rules (`src/finance/amortization.nova`)
- **Magnitudes, not signed cash flows.** Principal, payment, extra and lump sums are positive
  money, and rows report positive amounts. To use a TVM payment, which is negative, pass
  `money.negate(tvm.pmt(...))`.
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
- src/finance/tvm — PV/FV/PMT/N/IY, NPV/IRR
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
- **M2 — Amortization schedules only.** 🚧 in progress, awaiting review.
  - `src/finance/amortization.nova`: `schedule`, `schedule_with_extra`, `schedule_biweekly`.
  - Tests: `tests/finance/amortization_test.nova`, with Python vectors from
    `tests/finance/gen_amortization_vectors.py` and a row-by-row diff against
    `tests/finance/vectors/mortgage_200k_6_5_360.json`.
  - Not in M2: refinance, rent-vs-buy, extra-payment comparison logic.
- **M3 — NPV/IRR and uneven cash flows.**
- **Later — compound interest** (`investments`).
- **M4 — Scientific + units** (`core/math`).
- **M5 — Tkinter host:** screens with formula/assumptions, CSV export, terminal debug harness.
- **CI** (`.github/workflows/tests.yml`): `tools/run_tests.py` on every push and PR, plus a nightly
  `--bootstrap` job (cron, 07:17 UTC).
