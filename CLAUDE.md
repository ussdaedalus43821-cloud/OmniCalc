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
- Test command: `python3 tools/run_tests.py` (created in M0).
  Nightly CI only: `python3 tools/run_tests.py --bootstrap`.
- Formatter/linter: **none exists** (`novalang.py:4154`, `--bootstrap` is the only flag).
  Follow `Nova_Lang/CONTRIBUTING.md` "Style" by hand.
- Do NOT invent NovaLang syntax or stdlib. Cite docs/examples. Known gaps: no `**` (use `pow()`),
  no bitwise ops, `round()` is float half-even (don't use it for money).
- If NovaLang cannot express a platform feature, isolate that feature behind a thin adapter and document it.
- Prefer NovaLang for domain logic: math, finance, validation, and numeric formatting decisions
  (scale, rounding). The host turns the result into display strings.
- Use host-platform glue only when NovaLang has no supported path.

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

## Testing rules
- Tests are `tests/**/*.nova` using `check(label, actual, expected)`.
- Each test file ends with a guarded sentinel `print("TESTS_OK " + str(state["checks"]))` and never
  calls `len()` on the count.
- `tools/run_tests.py` runs every test file and fails on any of: non-zero exit, a missing sentinel,
  or a sentinel count that differs from the file's declared expected count.
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
- src/core/money.nova, rates.nova, dates.nova — foundation (M0)
- src/core/math — scientific, units, algebra hooks
- src/finance/tvm — PV/FV/PMT/N/IY, NPV/IRR
- src/finance/loans — amortization, extra payments, refinance
- src/finance/investments — compound interest (v1); CAGR, DCA, retirement (later)
- src/finance/business — margin, break-even, ROI, depreciation (post-v1)
- src/ui — Tkinter calculator screens (host)
- src/storage — presets, scenarios, local DB (post-v1)
- src/export — CSV (v1, host); PDF (post-v1)
- tools/run_tests.py — test runner
- tests/core, tests/finance — golden test vectors

## Milestones
- **M0 — Foundation only. No calculator modules.**
  - Add the submodule at `02eabdb` and the version assertion.
  - `money.nova`: minor units, scale, half-up rounding.
  - `rates.nova`: micro-unit rates, periodic rates with carried remainder.
  - `dates.nova`: serial days, add-months with EOM clamp, the three day-count conventions.
  - `tools/run_tests.py` with the sentinel and count check, plus tests for all three modules.
- **M1 — TVM:** PV/FV/PMT/N/rate, solve-for-any, NPV/IRR, golden vectors.
- **M2 — Loans:** amortization schedule, extra payments, refinance, schedule rows for CSV.
- **M3 — Compound interest** (`investments`).
- **M4 — Scientific + units** (`core/math`).
- **M5 — Tkinter host:** screens with formula/assumptions, CSV export, terminal debug harness.
- **CI:** test job on every push, nightly `--bootstrap` job.
