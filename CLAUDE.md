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
  - `type()` reports `"number"` for both ints and floats, so whole-number checks use
    `floor(x) == x`.
  - Built-in names (`min`, `max`, `sum`, `copy`, `remove`, `set`, `get`, ...) and keywords (`to`,
    `step`, `in`, `with`, `as`, `delete`) can't be used as variable or function names.
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
- **Rounding** is half-up, and only at cash-flow boundaries (each amortization period) and at
  display. Never round intermediate arithmetic.
- **Iterative solvers** (IRR, solve-for-rate) may use floats internally, but the objective is
  evaluated in minor units, and the result is verified at minor-unit precision before display.
- **Dates**: add-months with end-of-month clamping, 30/360, actual/365, actual/actual, and
  schedule generation all live in NovaLang.

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
- src/core/money.nova, rates.nova, dates.nova — foundation (M0)
- src/core/math — scientific, units, algebra hooks
- src/finance/tvm — PV/FV/PMT/N/IY, NPV/IRR
- src/finance/loans — amortization, extra payments, refinance
- src/finance/investments — compound interest (v1); CAGR, DCA, retirement (later)
- src/finance/business — margin, break-even, ROI, depreciation (post-v1)
- src/ui — Tkinter calculator screens (host)
- src/storage — presets, scenarios, local DB (post-v1)
- src/export — CSV (v1, host); PDF (post-v1)
- tools/run_tests.py — test runner; tools/check.nova — check() helper and sentinel
- tests/core, tests/finance — golden test vectors

## Milestones
- **M0 — Foundation only. No calculator modules.** ✅ done, awaiting review
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
- **M1 — TVM:** PV/FV/PMT/N/rate, solve-for-any, NPV/IRR, golden vectors.
- **M2 — Loans:** amortization schedule, extra payments, refinance, schedule rows for CSV.
- **M3 — Compound interest** (`investments`).
- **M4 — Scientific + units** (`core/math`).
- **M5 — Tkinter host:** screens with formula/assumptions, CSV export, terminal debug harness.
- **CI:** test job on every push, nightly `--bootstrap` job.
