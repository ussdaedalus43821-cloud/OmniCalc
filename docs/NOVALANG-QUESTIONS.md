# NovaLang — Questions for OmniCalc (Phase 0) — ALL RESOLVED

The facts below come from `ussdaedalus43821-cloud/Nova_Lang` at commit `02eabdb`
(branch `claude/bold-dirac-8owccb`). The answers are from the project owner's decision set of
2026-10-31, called **"Decisions 2026-10-31"** below. The binding rules derived from them are in
`CLAUDE.md`.

## What Phase 0 established

| Topic | Finding | Source |
|---|---|---|
| Version | v1.1.0 (`__version__ = "1.1.0"`) | `novalang.py:74`, `README.md` "Current release" |
| Implementation | Tree-walking interpreter on CPython 3.7+. No compiler, no build step | `README.md` "Quick start", "Self-hosting" |
| Run | `python3 novalang.py file.nova` (`--bootstrap` for the self-hosted engine) | `README.md` "Quick start" |
| Tests | No framework. `.nova` self-check scripts plus a direct-vs-bootstrap diff | `CONTRIBUTING.md` "Testing a change" |
| Package manager | None. Modules are imported by file path | `README.md` "Language syntax" |
| UI | None in the language. Only through a Python host | `README.md` "Embedding NovaLang in Python" |
| Numbers | `int` (arbitrary precision) or binary `float` | `novalang.py:418-431`. Verified: `0.1 + 0.2` → `0.30000000000000004` |
| Rounding | `round()` is Python's half-even float rounding | `novalang.py:1910-1914`. Verified: `round(2.5)` → `2` |
| Math | `abs round floor ceil sqrt pow sin cos tan ln log10 PI E min max sum`. No `**` (verified parse error), no bitwise ops | `README.md` "Standard library", `CHANGELOG.md` `[1.1.0]` |
| Dates | `time() now() format_time()` only | `README.md` "Standard library" |
| CSV | None. `split()` is not quote-aware (verified) | `README.md` "Standard library" |
| Formatter/linter | None. The only CLI flag is `--bootstrap` | `novalang.py:4154` |

## Resolutions (Decisions 2026-10-31)

| # | Question | Status | Decision |
|---|---|---|---|
| 1 | Target platforms | **Resolved** | Python-hosted desktop app. Web/mobile out of scope for v1. |
| 2 | How much is NovaLang | **Resolved** | All calculation logic in NovaLang. The Python host handles only UI, file I/O, CSV, datetime parsing/formatting and process launch. |
| 3 | UI toolkit | **Resolved** | Tkinter. No pygame. A terminal harness exists for debugging only, not as a product mode. |
| 4 | Money / decimal / rounding | **Resolved** | Integer minor units with a currency scale, end to end. Rates are integer micro-units (1e-6 of a fraction: 6.5% = `65000`). Periodic rate = annual / periods with the remainder carried, not pre-rounded. Round half-up only at cash-flow boundaries (per period) and at display. Iterative solvers may use floats internally, but the objective is evaluated in minor units and verified at minor-unit precision before display. No Python `decimal`. |
| 5 | Dates | **Resolved** | Hybrid. Python parses/formats, supplies "today", and passes `{y, m, d, serial}`. NovaLang does all date math on integer serial day numbers: add-months with end-of-month clamping, 30/360, actual/365, actual/actual, schedule generation. |
| 6 | CSV | **Resolved** | Export only in v1, using Python's `csv` module in the host. NovaLang returns rows as arrays of integers plus a scale. No NovaLang CSV parser. |
| 7 | Pinning | **Resolved** | Git submodule at `02eabdb`, plus a startup assertion that the version is `1.1.0`. |
| 8 | `--bootstrap` parity | **Resolved** | Separate nightly CI job. Not required locally, not a correctness gate. |
| 9 | Test convention | **Resolved** | Keep the `check(label, actual, expected)` style. Each test file ends with a `TESTS_OK <n>` sentinel that doesn't call `len()` on a number. A Python runner fails on non-zero exit, a missing sentinel, or a check-count mismatch. Don't patch the submodule; report the upstream bug separately. |
| 10 | v1 scope | **Resolved** | Scientific, units, TVM, amortization, compound interest, amortization CSV export. No tax in v1. |
| 11 | Performance | **Resolved** | NovaLang everywhere except documented heavy jobs. UI-path budget: 100 ms / about 10k interpreter steps. Anything over that moves to Python behind the same interface, with a parity test against the NovaLang version. |

## Upstream issue (reported; do not patch the submodule)
`Nova_Lang/examples/stdlib_full_test.nova`: the failure-report branch calls `len(state["checks"])`
on a number, so the summary crashes if any check fails.
Filed as https://github.com/ussdaedalus43821-cloud/Nova_Lang/issues/2. OmniCalc is unaffected
because it uses its own `TESTS_OK` sentinel (`tools/check.nova`, `tools/run_tests.py`).
