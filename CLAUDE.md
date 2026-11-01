# OmniCalc — Claude Code Rules

## Project
OmniCalc is a modular calculator: math engine + finance engine + UI + local storage + export.
v1 is a **Python-hosted desktop app with a Tkinter UI**. Web/mobile are out of scope.
The decision record is in `docs/NOVALANG-QUESTIONS.md` ("Decisions 2026-10-31").

## NovaLang rules
- NovaLang version: **v2.0.0**, pinned as a git submodule at `vendor/Nova_Lang` (commit `bd5d502`).
  At startup the host asserts that the interpreter version is `"2.0.0"` (`novalang.py:88`).
  Never patch the submodule; report upstream issues instead.
- Runtime: `novalang.py` on CPython 3.7+. Since 2.0.0 it compiles every program to bytecode and
  runs it on a VM (`Nova_Lang/README.md` "Architecture"). The 1.1.0 tree-walking interpreter still
  ships as the fallback and the reference the VM is tested against byte for byte: `--tree-walk` on
  the command line, `Nova(engine="tree")` when embedding. The host embeds it through the `Nova`
  class (`README.md` "Embedding NovaLang in Python") on the default engine, the VM.
- **Type gate:** a program that imports modules (every OmniCalc façade and test) is type-checked
  before it runs (`README.md` "Type annotations"). OmniCalc has no annotations, so there are no
  contracts to break, and nothing is refused; the cost is startup time, about 0.2 s for the six
  engines `app.warm_up()` builds. Each interpreter checks a module once.
- Build command: **none.** Compiling happens at load time; there is no build step.
- Test command: `python3 tools/run_tests.py` (runs the pin check, then every `tests/**/*.nova`),
  then `python3 -m unittest discover -s tests/host -p "*_test.py" -t .` for the host. Both run in
  CI.
  Nightly CI only: `python3 tools/run_tests.py --bootstrap` (about 50x slower; the dates test
  takes about 50 s).
- Toolchain: since 2.0.0 `novalang.py` has `--format` (formatter), `--check` (linter),
  `--typecheck`, `--dis` (bytecode), `--tree-walk` and `--bootstrap` (`novalang.py:6366-6400`,
  `README.md` "Toolchain: formatter & linter"). OmniCalc has not adopted the formatter or linter
  yet; until it does, follow `Nova_Lang/CONTRIBUTING.md` "Style" by hand.
- Do NOT invent NovaLang syntax or stdlib. Cite docs/examples. Known gaps and traps (each one
  re-verified on v2.0.0 on both engines; none changed):
  - There is no `**` operator (use `pow()`), no bitwise ops, and no `null` literal.
  - `round()` is float half-even; never use it for money.
  - `/` returns a float when the division is inexact (`binary_operation`, `novalang.py:2959-2966`).
    Integer code uses only `+ - * // %`; `//` floors (`novalang.py:2967-2970`).
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
  - **`PI`, `E` and `json` are undefined inside imported modules**; only the top-level script
    has them.
    - For `PI` and `E`, use the literals `3.141592653589793` and `2.718281828459045`, which are
      bit-identical.
    - For `json`, decode in the host or in a top-level script and pass the parsed data in, as
      `units.load(data)` does.
  - **`log` is the stderr logger, not a logarithm,** and there's no `exp`, `asin`, `acos` or
    `atan`. See `src/math/scientific.nova` for NovaLang versions.
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

## Bridge contract: no math in Python (M4)
- **The host does zero arithmetic.** `src/host/app.py` hands NovaLang the input boxes **as
  typed** (strings). `src/app/amortization_screen.nova`'s `calculate()` parses them
  (`src/core/parse.nova`, never rounding) and returns only integers, scales and strings,
  including schedule rows as integer lists plus one scale.
- The host formats integer + scale as text (`format_minor`), draws it, and writes CSV.
- **Enforced:** `tests/host/bridge_test.py` parses `app.py` and fails on any arithmetic
  operator outside `app.ARITHMETIC_ALLOWED`, which is formatting (`format_minor`), timing
  (`elapsed_ms`) and smoke-test click delays (`parse_args`). String and list concatenation
  are allowed. It caught an `argv.index(...) + 1` on its first run.
- **Proved:** the same test compares `app.calculate(...)` with
  `tools/calc_cli.nova` run through the plain interpreter. They must be identical.
- **Speed:** `app.calculate` must finish within the 100 ms budget. The test takes the best of
  3; CI sets `OMNICALC_BUDGET_MS=300` for runner noise. `OMNICALC_DEBUG=1` logs every press.
  `app.warm_up()` runs one calculation at startup, because a cold first call is about 50%
  slower.
- **Running the app:** Tkinter isn't on pip. On Ubuntu, `apt install python3-tk` (for
  `/usr/bin/python3.12`), then `python3.12 src/host/app.py`. The calculation path imports
  without Tkinter or a display.

## Screens and navigation (decided before screen two, M5)
- **One window, one `ttk.Notebook` tab per screen.** Tabs are the standard pattern for a calculator
  suite: cheap, familiar, uncluttered, and each tab keeps its widgets, so **inputs and results
  survive switching**.
- **No auto-calculate.** A tab recalculates only on **Calculate** (or Enter). Editing any input marks
  its results **stale** ("Inputs changed - press Calculate…") until then.
- A screen is one entry in `app.SCREENS`: its façade file, its input fields (as `calculate()` takes
  them), and its summary items with a display kind (`money`, `count`, `percent`, `text`,
  `phrase`).
  - Field kinds: a text entry (the default), a **choice** (a read-only drop-down whose *value*
    goes to the façade), **rows** (an editable list with Add row / Remove last row, which goes to
    the façade as a list of lists of strings), and **hidden** (data the host loaded, such as the
    parsed units table, passed through with no widget).
  - A **phrase** is `{before, amount, after}`: the façade decides how a number reads ("saves X" /
    "costs X MORE"), and the host only formats the amount, which may be absent.
  - **`decimal`** is `{value, scale}`, e.g. fractional shares. A `percent` with no value (`{}`)
    shows as "-". A façade may return **`extra_tables`** (`[{title, columns, column_kinds,
    rows}]`), drawn below the main table; CSV exports the main table only. The table
  and CSV come from the façade's `columns`, `column_kinds` and `rows`, so one exporter serves every
  screen.
- Each screen gets **its own NovaLang engine**, because every façade exports `calculate`. Startup
  warms up all of them.

## Screen façades: one is a pattern, two is evidence
- A façade (`src/app/<screen>_screen.nova`) exports `calculate(<input boxes as strings>)` and returns
  `{currency, scale, <summary fields>, columns, column_kinds, rows, assumptions}`. It holds all the
  screen's parsing and math.
- **Don't generalize on N = 1.** M4 had one façade, so nothing was abstracted.
- **Evidence from M5 (N = 3):** the host side generalized with **no change to the contract**,
  except adding `column_kinds`. One `SCREENS` loop, one exporter, one CLI dispatcher, one bridge
  test, and the arithmetic guard passed unchanged.
- **Extracted in M6:** `src/app/parse_helpers.nova` (`amount`, `annual_rate_micro`,
  `monthly_rate`, `count` and the `CURRENCY`/`SCALE` constants), with
  `tests/app/parse_helpers_test.nova` pinning every edge case.
  - **Drift found before extracting:** the amortization façade's `amount()` accepted negative
    amounts, leaving `amortization.nova` to reject them later with a different message. Every
    façade now rejects them at parse time.
  - Whether a negative *rate* is allowed is a domain choice, so it's a parameter
    (`allow_negative`), not a copy. Savings allows rates above −100%; loans don't.

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
  **One deliberate exception: goal-seeking.** A solved savings contribution must *reach* the goal,
  so it rounds **up**, with `money.round_ceiling` on `tvm.pmt_exact`. Solved periods round up too.
  Use the ceiling nowhere else.
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
  - `cashflow.irr(from_schedule(s))` (checked) / `cashflow.schedule_irr(s)` (unchecked core
    `shape_whole`, for schedules built by `amortization.nova`). This cut end to end from
    89 ms to 60 ms. A test checks that both agree.
  - `investments.position_summary` / `position_summary_whole` (M7, for lots the screen just
    built from parsed values), and `investments.allocation` / `allocation_of_values`.
  - `amortization.schedule*` (money rows) / `amortization.schedule_table` (the int-row core
    `table_whole`, after the same input checks), plus `cashflow.table_irr(table, guess)`. It
    builds the IRR polynomial straight from the int rows and starts bisection from a
    3-micro-unit bracket around the guess, falling back to the full search. The amortization
    screen dropped from 56.7 to 40.5 ms. Tests check agreement with the money-row path, and that
    a bad guess falls back correctly.

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
- **`V = 0`:** no root at any rate above −100%, so `irr` returns `[]` without searching.
  Descartes bounds the *positive* roots of `P(x)`, and `x > 0` is exactly `r > −100%`, the
  whole domain. A root at `x < 0` would be a "rate" below −100%, which is meaningless. Put
  financially: a single-sign flow's NPV is never zero at any rate above −100%.
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
  - **Hard caps:** V ≥ 2 flows over **60 periods** (about 270 ms) are refused with an error
    that names the cap, says why, and points to `docs/ESCAPE-HATCHES.md`, where a planned
    escape hatch is tracked. Independently, the search stops after 400 Budan counts and
    200 bisection steps per root.
- **`irr_min_nonneg`** returns the smallest root **≥ 0**, so 0% counts: [−100, +100] → 0%, as
  in Excel. It throws only when no root ≥ 0 exists.
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

## XNPV / XIRR convention (`src/finance/cashflow.nova`, M4)
- **Excel's convention, and only Excel's.** v1 offers no alternatives.
  - A dated flow is `{date_serial, amount}`. `d_0` is the **first flow's** date, and a later
    flow dated before it throws (Excel gives #NUM!).
  - Each flow is discounted by `(1 + rate)^(days / 365)`, where
    `days = dates.day_count_actual_365(d_0, d_i).days` (actual/365, "a 365-day year").
  - `rate` is an **annual** effective rate, unlike `npv`/`irr`, whose rate is per period.
- **Floats for the discount factor only.** It's irrational, so this is a known approximation in
  `docs/ESCAPE-HATCHES.md`. Amounts stay integer, and the result is rounded half-up once.
- **XIRR.** Descartes' rule on the flows in date order:
  - V = 0 throws;
  - V = 1: bracket, then the **Illinois method** in floats (M7; about 10 evaluations where
    bisection needed about 40), converging on the *rate*. `xirr_from_guess(flows, guess)`
    skips the outward bracket walk by trying a ±500 bp window around a guess first. The
    investments screen guesses value ÷ cost annualized over first purchase → as-of. A guess with
    no sign change in its window falls back to the full search; tests pass −50% and +900% guesses
    and check the answer is unchanged. The answer must leave an XNPV within
    one minor unit of zero, or it falls back to bisection. Stopping early "once XNPV is under half
    a minor unit" was tried and rejected: with small amounts it only pins the rate to about 1e-6,
    and the reference tests caught it;
  - **V ≥ 2 throws**, because Budan doesn't apply when the degree is a day count. A planned
    escape hatch is tracked.
- **References:** Microsoft's XNPV/XIRR example (XNPV(9%) = 2,086.65, XIRR 0.373362535,
  where Excel is only good to 1e-8) and `tests/finance/gen_xcashflow_vectors.py` (50 digits).

## Savings convention (`src/app/savings_screen.nova`, M5; solve-for in M6)
- **Solve for any variable.** `mode` selects what to solve for:
  - `fv`: the final balance;
  - `pmt`: the monthly contribution needed to reach a target in N years;
  - `n`: the time to reach a target. This is `tvm.n`'s `periods`, the first whole month the
    balance reaches the target. The last row stops at that month.
  Inputs a mode doesn't use are ignored.
- **Solved contributions round up so the goal is reached; solved periods round up for the same
  reason** (decided after M6). $1,000,000 in 30 years at 7% is exactly 753.1614…/month: half-up
  would give 753.16 and land $1.67 short. Rounded up, 753.17 lands at $1,000,010.53, and the screen
  shows the margin ("reaches the target with 10.53 to spare").
- Time to goal also checks the reported month really reaches the target. `tvm.n`'s `periods`
  ignores a sub-1e-4 overshoot, so the façade adds a month if needed.
- Contributions are made at the **end of each month** (an ordinary annuity), matching the loan
  payment convention. **Start-of-month is deliberately not offered in v1.**
- Monthly rate = annual / 12, kept exact. Each year's balance is `tvm.fv`, rounded half-up to the
  cent. Interest earned = balance − (initial deposit + contributions so far).
- Rejected: an annual rate ≤ −100%, fractional or out-of-range years (1–100), and negative amounts.
- Checked against `tests/app/gen_savings_vectors.py`, which uses the textbook FV formula at 80 digits.

## Refinance convention (`src/finance/refinance.nova`, M5)
- **Closing costs are all-in** (points, appraisal, title, everything). They are paid out of pocket
  at period 0 and **not amortized** into the new loan, whose principal is the current principal.
- The new payment is `tvm.pmt` at the new rate and term. Both loans run through
  `amortization.schedule_table`, so final adjustments count. Month k's saving = current payment −
  new payment, each 0 once its loan is paid off.
- **Break-even** = the smallest month k ≥ 1 where the cumulative saving ≥ the closing costs.
  NovaLang has no null, so the result carries `breaks_even: bool` and `break_even_month` (0 when
  it never breaks even).
- **`lifetime_savings` is the headline**: current total paid − (new total paid + closing). "Should I
  refinance?" is a question about total dollars over the loans' lives. The façade returns it as a
  phrase, "saves X over both loans' lives" or "costs X MORE than keeping the current loan", so a
  loss can never read as a saving.
- **`savings_over_remaining_term`** (renamed in M6 from `total_savings`, which was misleading) sums
  the savings over the **shorter** schedule, minus closing costs. It's a secondary sanity check,
  labelled "Net over the shorter term only". When the terms differ it can disagree with lifetime,
  even in sign:
  - 30 → 15 years: −$63,140.28 vs a lifetime saving of +$164,400.34;
  - a fresh 30-year five years in: +$90,651 vs +$33,731.
- **Throws** when the new rate is not lower **and** the new payment is not lower: nothing is saved,
  so there's no break-even.

## Debt payoff convention (`src/finance/debt_payoff.nova`, M6)
- A debt is `{name, balance, rate, minimum_payment}`: positive money, and a rate **per month** above
  −100%. `monthly_budget` must cover the sum of the minimums **and** exceed the first month's
  total interest. The plan must finish within 1,200 months.
- **Each month:**
  1. every open debt accrues interest (balance × rate, rounded half-up);
  2. every open debt gets its minimum, or its balance if that's smaller;
  3. **all** the rest of the budget goes to the first open debt in strategy order, cascading to
     the next one in the same month when a debt clears.
- **Rollover:** the whole budget is paid every month but the last, so a paid-off debt's minimum
  rolls into the target. That is what makes snowball and avalanche differ.
- **Order is fixed at the start:**
  - snowball = balance ascending;
  - avalanche = rate descending;
  - ties keep the input order.
  With equal rates the orders differ but total interest doesn't. A test pins $3,643.60 both ways.
  On realistic debts avalanche wins; a test pins a gap of $485.47.
- **Cost** is debts × months, about 45 µs per debt-month per strategy, and the screen runs both
  strategies. Inlining the rounding was measured and gained nothing beyond noise, so it calls the
  one rounding rule.

## Investments convention (`src/finance/investments.nova`, `src/app/investments_screen.nova`, M7)
- **Lots:** a lot is `{date_serial, shares, price_per_share}`. Shares are an exact fraction
  `{num, den}`, typed with up to 6 decimals and never a float.
- **Rounding:** cost basis and value are summed exactly over a position's lots and rounded
  half-up **once** per position, so every total equals the sum of its rows.
- **CAGR** = (final / initial)^(1 / years) − 1, with fractional years (days / 365). It uses a float
  power, which is a known approximation like XNPV. It's checked against Excel's RRI example
  (RRI(96, 10000, 11000) = 0.0009933) and a 50-digit reference.
- **Allocation:** integer basis points summing to **exactly** 10,000, by largest remainder.
- **The screen:**
  - Rows are purchase lots; several rows with one symbol form one position and must agree on the
    current price. Prices are typed, never fetched (offline-first).
  - Dates are parsed in NovaLang (`parse_helpers.date`). The host only fills in today's date as
    text.
  - **Annualized return per position:** one dated lot uses CAGR. Several dated lots use XIRR,
    because a position bought on several dates has no single CAGR; for one lot the two are
    identical under actual/365.
  - The **portfolio** figure is XIRR over every lot, shown only when every lot has a date.
- **No persistence**, no history, no live prices in M7. Those are M8+ decisions.
- **Speed:** a 24-lot, 20-position portfolio took 136 ms; after the unchecked cores, Illinois
  XIRR and a **guessed-start XIRR** it's **about 72–85 ms median** in this container. That meets
  the portfolio-screen target (< 90 ms). `tools/perf.py` monitors it as the `investments_20`
  scenario.
- **The per-position annualized return stays,** even though the brief didn't ask for it: "which
  position is my best performer?" is what a portfolio screen is for. Features aren't cut to hit a
  budget.

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
- UI-path budget: **100 ms per button press**, roughly 10k interpreter steps (interpreter speed is
  about 162k steps/s, `Nova_Lang/README.md` "ECS & particle engine"; measured on 1.1.0's
  tree-walker. The 2.0.0 VM runs NovaLang's loop benchmark about 2.6x faster, and OmniCalc's
  screens 1.2-1.6x faster, so the step estimate is conservative).
- **Calculate-path median targets** (decided after M7):
  - **under 70 ms for single-schedule screens** (amortization, savings, refinance, debt payoff);
  - **under 90 ms for portfolio screens** (investments).
  Why: the 70 ms target dates from M4 and assumed amortization-style work. A portfolio press runs
  one XIRR per multi-lot position plus a portfolio XIRR and an allocation. The hard limit is still
  100 ms per press.
- **Profile before writing a screen.** Before writing a new screen, profile the backing
  module's hot path with a synthetic worst-case input. If it's already over 50 ms, design the
  unchecked-core path from the start, rather than discovering it after the façade is written.
  M7 skipped this step and then had to chase 136 ms down to about 75 ms.
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
  interpreter reports `__version__ == "2.0.0"` and that the submodule HEAD is `bd5d502...`.
- **Engine parity:** `python3 tools/run_tests.py --tree-walk` runs every test on the
  tree-walker instead of the VM. Both must pass with identical output; it was run for the
  2.0.0 upgrade.
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
- src/math/scientific.nova — expression evaluator, exact rationals, float functions, display (M8)
- src/math/units.nova + units.json — exact unit conversion over a checked-in table (M8)
- src/math/datetime.nova — durations, business days, day-count conventions (M8)
- src/app/math_screen.nova — the Math tab's façade (M8)
- src/finance/tvm.nova — PV/FV/PMT/N/rate (M1)
- src/finance/cashflow.nova — NPV, IRR, payback, from_schedule (M3)
- src/finance/amortization.nova — schedules, extra payments, biweekly (M2); schedule_table (pre-M5)
- src/finance/refinance.nova — keep vs refinance comparison (M5)
- src/finance/debt_payoff.nova — snowball / avalanche plans (M6)
- src/app/parse_helpers.nova — shared façade input parsing (M6; shares and dates in M7)
- src/finance/investments.nova — positions, gains, CAGR, allocation (M7)
- src/finance/investments — compound interest (v1); CAGR, DCA, retirement (later)
- src/finance/business — margin, break-even, ROI, depreciation (post-v1)
- src/app — NovaLang screen façades (one per screen; all the screen's math)
- src/host/app.py — the Tkinter host (formatting, drawing, CSV only)
- src/storage — presets, scenarios, local DB (post-v1)
- src/export — CSV (v1, host); PDF (post-v1)
- tools/run_tests.py — test runner; tools/check.nova — check() helper and sentinel
- tests/core, tests/finance, tests/app — golden test vectors (.nova); tests/host — host tests (Python)

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
- **M3 — NPV/IRR and uneven cash flows.** ✅ done, reviewed.
  - `src/finance/cashflow.nova`: `npv`, `irr` (all roots found), `irr_min_nonneg` (renamed
    from `irr_min_positive`; 0% counts), `payback` (undiscounted, linearly interpolated),
    `from_schedule`, and `schedule_irr` (the unchecked core, added before M4).
  - Tests: `tests/finance/cashflow_test.nova`, with Python vectors from
    `tests/finance/gen_cashflow_vectors.py`.
  - Not in M3: XNPV/XIRR, which need dated flows.
- **M4 — XNPV/XIRR, dates-based cash flows, and the start of the UI host.** ✅ done, reviewed.
  - `cashflow.xnpv`, `cashflow.xirr` (Excel convention; XIRR supports one sign change).
  - Host:
    - `src/core/parse.nova`, `src/app/amortization_screen.nova` (the screen's one façade);
    - `src/host/app.py` (one Tkinter screen: inputs, summary, schedule, Export CSV);
    - `tools/calc_cli.nova`.
  - Tests: `tests/core/parse_test.nova`, `tests/app/amortization_screen_test.nova`, and
    `tests/host/bridge_test.py` + `csv_test.py`, which CI runs with `unittest`.
- **M5 — two more screens (savings, refinance) and the multi-screen shell.** 🚧 in progress,
  awaiting review.
  - Pre-M5: `schedule_table` + `table_irr` (56.7 → 40.5 ms); the navigation decision; the façade
    note above.
  - `src/finance/refinance.nova`, `src/app/savings_screen.nova`,
    `src/app/refinance_screen.nova`, and `app.py` as a three-tab Notebook.
  - Tests:
    - `tests/finance/refinance_test.nova` (vectors: `gen_refinance_vectors.py`);
    - `tests/app/savings_screen_test.nova` (vectors: `gen_savings_vectors.py`);
    - `tests/app/refinance_screen_test.nova`;
    - the host tests, now covering all three screens.
  - Nightly performance monitor: `tools/perf.py` plus a CI job that uploads `perf-results.json`
    and fails only the nightly job on a >20% median regression vs `tools/perf_baseline.json`.
- **M5** ✅ done, reviewed.
- **M6 — debt payoff and gap-fills.** ✅ done, reviewed. Merged to `main` as `v0.1.0` (PR #1).
  - Gap-fills:
    - savings solve-for (FV / PMT / N);
    - `total_savings` → `savings_over_remaining_term`, with lifetime as the headline;
    - `parse_helpers.nova` extracted;
    - refinance p90 measured: 66–73 ms over four 100-press runs, under 80, so not optimized;
    - the CI perf baseline committed.
  - `src/finance/debt_payoff.nova` and `src/app/debt_payoff_screen.nova` (a fourth tab).
  - The two planned escape hatches moved to M7 or later; neither is needed by these screens.
- **Pre-M7:**
  - solved savings goals round up (`money.round_ceiling`, `tvm.pmt_exact`);
  - the 10+ debt trigger was recorded;
  - PR #1 merged to `main`;
  - the perf gate was calibrated (raw ms false-alarmed across runners).
- **M7 — investments (Option A).** 🚧 in progress, awaiting review.
  - `src/finance/investments.nova`, `src/app/investments_screen.nova` (a fifth tab, with an
    allocation table as an `extra_tables` entry).
  - Tests: `tests/finance/investments_test.nova` (vectors: `gen_investments_vectors.py`) and
    `tests/app/investments_screen_test.nova`, which diffs a 20-position portfolio against
    `tests/app/vectors/portfolio_20.json` (`gen_portfolio_vectors.py`).
- **M7** ✅ done, reviewed; merged to `main` (PR #2, `ab8dd8b`).
- **M8 — math engine.** ✅ implemented, awaiting review. The API is in `docs/M8-MATH-DESIGN.md`.
  - **`src/math/scientific.nova`:** an exact-first evaluator with a hand-written tokenizer,
    recursive descent and its own display. 112 checks against `tests/math/gen_math_vectors.py`.
  - **`src/math/units.nova`:** exact conversions over `src/math/units.json` (84 units,
    11 categories, every factor exact by definition and re-derived independently by the
    generator). 53 checks, and 1 psi → Pa must be the exact fraction.
  - **`src/math/datetime.nova`:** durations, business days with a holiday list (Excel WORKDAY
    semantics; counting over (a, b]), and five day-count conventions with exact fractions. 69
    checks against `tests/math/gen_datetime_vectors.py`.
  - **`src/app/math_screen.nova`** and a **Math tab** (expression, angle mode, unit converter, and
    a table of the value in every unit of its category). The host passes the parsed units table
    as a hidden field. 11 façade checks, plus host CLI parity and a CSV round trip.
  - **Grammar conventions (approved, each pinned by a test):**
    - `-2^2 = -4`;
    - `^` is right-associative;
    - no implicit multiplication (`2pi` is an error);
    - 12 significant figures, with scientific notation at an exponent ≥ 12 or ≤ −7.
  - **Mutation-tested:** each mutation is caught by named failing cases.
    - scientific: left-associative `^`, implicit multiplication, Excel-style unary minus,
      half-even rounding, float literals;
    - units: offset sign, inverted factors, case-insensitive lookup, float arithmetic;
    - datetime: inclusive counting, the 30/360 D1 condition, single-basis act/act, months rounded
      up, the weekday origin.
- **NovaLang 2.0.0 upgrade.** ✅ The submodule moved from v1.1.0 (`02eabdb`) to v2.0.0
  (`bd5d502`), the bytecode VM. All 740 NovaLang checks and 18 host tests pass on the VM and on the
  tree-walker, with byte-identical output from every test file. Screens are 1.2-1.6x faster
  (median; PR description has the table); startup is slower (see "Type gate" above). The dry
  run found NovaLang's type gate re-checking shared modules (159 checks for 37 loads); it was
  fixed upstream before the pin moved.
- **Later — compound interest** (`investments`).
- **Later — Scientific + units** (`core/math`).
- **Later — the full Tkinter host:** screens with formula/assumptions, CSV export, a terminal debug
  harness.
- **CI** (`.github/workflows/tests.yml`):
  - on every push and PR: `tools/run_tests.py` and the host `unittest` suite;
  - nightly (cron, 07:17 UTC): the `--bootstrap` job and the performance monitor.
  - **Performance baseline:** `tools/perf_baseline.json` comes from a CI run's log, never from a
    dev machine.
  - **Calibrated:** hosted runners vary up to about 1.8× between runs. Every screen, including
    unchanged code, ran 1.74–1.82× slower on one runner than on another. So each run also times a
    fixed NovaLang workload, and the gate compares each screen's **median ÷ calibration**
    (`relative`), alerting at +20%.
  - **After the 2.0.0 upgrade** the screens got faster but the calibration workload did not
    (its `acc["total"] = ...` index assignment has no VM fast path; it runs at tree-walker
    speed), so every relative value dropped (amortization 0.28 → 0.16 here). The old baseline
    cannot false-alarm, but it would only alert once a screen got about 2x slower. Re-baseline
    from CI after the upgrade merges.
  - The relative values carry across machines: CI 0.360 / 0.140 / 0.533 / 0.123 vs this container
    0.37 / 0.15 / 0.57 / 0.13, with raw speeds 1.5× apart. The perf job also
    runs on push, but only reports there (`continue-on-error`). To re-baseline, run the workflow
    with `update_baseline: true`, which opens a PR. That needs the workflow on the default branch
    and "Allow GitHub Actions to create and approve pull requests" enabled; otherwise, copy the
    JSON from the job log.
