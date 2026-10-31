# OmniCalc — Claude Code Rules

## Project
OmniCalc is a modular calculator: math engine + finance engine + UI + local storage + export.

## NovaLang rules
- NovaLang version: **v1.1.0** (`Nova_Lang/novalang.py:74`, `__version__ = "1.1.0"`, commit `02eabdb`).
  Pinning mechanism: TBD — see `docs/NOVALANG-QUESTIONS.md` Q7.
- Runtime/compiler: tree-walking interpreter `novalang.py` on CPython 3.7+. There is no compiler
  (`Nova_Lang/README.md` "Quick start", "Self-hosting"). Run: `python3 novalang.py <file>.nova`;
  self-hosted check: `python3 novalang.py --bootstrap <file>.nova`.
- Build command: **none** — NovaLang has no build step (`Nova_Lang/README.md` "Quick start").
- Test command: **not yet defined.** NovaLang has no test framework; its convention is `.nova`
  self-check scripts plus direct-vs-`--bootstrap` diffs (`Nova_Lang/CONTRIBUTING.md` "Testing a change").
  A runner (proposed: `python3 tools/run_tests.py`) is a Milestone 0 deliverable; update this line then.
- Formatter/linter: **none exists.** `novalang.py`'s only CLI flag is `--bootstrap` (`novalang.py:4154`).
  Follow `Nova_Lang/CONTRIBUTING.md` "Style" by hand.
- Do NOT invent NovaLang syntax or stdlib. Cite docs/examples.
- If NovaLang cannot express a platform feature, isolate that feature behind a thin adapter and document it.
- Prefer NovaLang for domain logic: math, finance, validation, formatting.
- Use host-platform glue only when NovaLang has no supported path.

### Known NovaLang gaps → adapters / libraries (verified in Phase 0)
| Need | NovaLang status | Plan |
|---|---|---|
| Decimal money | Only binary floats + arbitrary-precision ints (`novalang.py:418-431`) | Fixed-point decimal library in NovaLang on ints (pending Q4) |
| `**` operator | Not supported (parse error); use `pow()` | — |
| Rounding | `round()` = Python float half-even | Own decimal rounding in the decimal library |
| Dates | Only `time()`, `now()`, `format_time()` | Pure-NovaLang date library (pending Q5) |
| CSV | None; `split()` is not quote-aware | NovaLang CSV writer over `write()` (`README.md` "Standard library") |
| UI | None | Host adapter (pending Q1/Q3) |
| PDF | None | Host adapter (`src/export`), later milestone |
| Local DB | Only filesystem + `json.dumps/loads` | JSON files via `src/storage` |

## Engineering rules
- Money uses decimal arithmetic, never binary floats.
- Every finance calculator must support “solve for any variable.”
- Every loan calculator must generate an amortization schedule.
- Every result screen must show formula/assumptions and allow CSV export.
- No ads, no tracking, offline-first.
- All core finance math must have deterministic tests with known values.
- Do not build the whole app at once. Work milestone by milestone.

## Architecture
- src/core/math — scientific, units, algebra hooks
- src/finance/tvm — PV/FV/PMT/N/IY, NPV/IRR
- src/finance/loans — amortization, extra payments, refinance
- src/finance/investments — compound interest, CAGR, DCA, retirement
- src/finance/business — margin, break-even, ROI, depreciation
- src/ui — calculator screens
- src/storage — presets, scenarios, local DB
- src/export — CSV/PDF
- tests/finance — golden test vectors
