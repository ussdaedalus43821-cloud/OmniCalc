# NovaLang — Open Questions for OmniCalc (Phase 0)

Source inspected: `ussdaedalus43821-cloud/Nova_Lang`, branch `claude/bold-dirac-8owccb`
(HEAD `02eabdb`). OmniCalc contains only `README.md`; there is no `docs/NOVALANG.md`
in either repo. All NovaLang facts below cite files in the Nova_Lang repo.

## What is established

| Topic | Finding | Source |
|---|---|---|
| Version | v1.1.0, set only inside the interpreter (`__version__ = "1.1.0"`) | `novalang.py:74`, `README.md` "Current release", `CHANGELOG.md` `[1.1.0]` |
| Implementation | Tree-walking interpreter in Python 3.7+; no compiler, no build step | `README.md` "Quick start", "Self-hosting" |
| Run | `python3 novalang.py file.nova` (also `--bootstrap`) | `README.md` "Quick start" |
| Tests | No test framework; `.nova` self-check scripts plus a direct-vs-`--bootstrap` diff | `CONTRIBUTING.md` "Testing a change" |
| Package manager | None. Zero dependencies; modules are file-path `import "./x.nova"` | `README.md` "Quick start", "Language syntax" (modules) |
| UI | None in the language. UI only exists via a Python host (pygame examples) | `README.md` "Embedding", `examples/ecs_demo.py` |
| Numbers | One `number` type: Python `int` (arbitrary precision) or binary `float` | `novalang.py:418-431`; verified: `0.1 + 0.2` → `0.30000000000000004` |
| Rounding | `round()` is Python's (half-to-even, float-based): `round(2.5)` → `2`, `round(2.675, 2)` → `2.67` | `novalang.py:1910-1914`; verified |
| Math | `abs round floor ceil sqrt pow sin cos tan ln log10 PI E min max sum`; no `**`, no bitwise ops | `README.md` "Standard library"; `CHANGELOG.md` `[1.1.0]` (no bitwise) |
| Dates | `time() now() format_time(t, fmt)` only; no date parsing or date arithmetic | `README.md` "Standard library" |
| CSV | No CSV support. `split()` doesn't handle quoted fields | `README.md` "Standard library"; verified |
| Decimal | None built in. `decimal` isn't on the `python.import` allowlist (`datetime` is) | `README.md` "Security" |

## Resolved by CLAUDE.md
- Q4 (partial): money must use decimal arithmetic, never floats. Still open: implementation
  (fixed-point ints in NovaLang vs. host `decimal`) and rounding rule.
- Q6: CSV export is required on every result screen.
- Q10 (partial): module layout is fixed by CLAUDE.md "Architecture"; v1 milestone order still open.
- New: PDF export and local storage are required; both need host adapters or JSON-on-filesystem.

## Questions — please answer before any app code

1. **Target platforms.** NovaLang runs only where CPython runs. It has no web/iOS/Android
   target. Is OmniCalc a desktop/CLI app (Python host + NovaLang), or did you expect
   web/mobile? If web/mobile, which host (e.g. Pyodide in the browser)? This hasn't been
   tested and isn't documented.
2. **How much is NovaLang?** Options:
   (a) all logic in NovaLang, with a thin Python host for UI/IO;
   (b) a pure NovaLang CLI/REPL app (no GUI);
   (c) something else.
   Which one?
3. **UI toolkit.** If there's a GUI, which Python toolkit should host it (Tkinter is stdlib
   and needs no dependencies; pygame is what the repo's examples use)? Or should it be
   terminal-only?
4. **Money and decimal precision.** NovaLang has only binary floats. Pick one:
   (a) fixed-point integer arithmetic in NovaLang (e.g. cents or 10⁻⁸ units; ints are
   arbitrary precision);
   (b) the host exposes Python `decimal` via `Nova.expose_module(...)` / `expose()`;
   (c) accept float with display rounding (not recommended for finance).
   And what rounding rule: half-up, half-even (banker's), or one per calculator?
5. **Dates.** Loan schedules and date math need date parsing and day counts. Should I
   write a pure-NovaLang date library (civil-date ↔ day-number, add months, day-count
   conventions), or use `python.import("datetime")`? The latter only works when embedded,
   not with plain `novalang.py`.
6. **CSV.** Is CSV import/export needed in v1? If so, should it be a NovaLang CSV parser
   (RFC 4180 quoting) on top of `read`/`write`, or should the Python host's `csv` module
   pass rows in?
7. **Pinning NovaLang.** No package manager exists. How should OmniCalc pin v1.1.0:
   a git submodule at commit `02eabdb`, a vendored copy of `novalang.py` (+ `novalang.nova`),
   or a documented sibling checkout?
8. **`--bootstrap` parity.** Must OmniCalc's NovaLang code also pass under the self-hosted
   interpreter (`--bootstrap`), as Nova_Lang's own examples do, or is the host engine enough?
9. **Test convention.** Is the repo's `check(label, actual, expected)` self-check script
   pattern (`examples/stdlib_full_test.nova`), run by a shell/Python runner, acceptable as
   OmniCalc's test framework?
10. **Scope of v1.** Which calculators come first? Examples: arithmetic/scientific,
    unit conversion, loan/amortization, compound interest/savings, budgeting, NPV/IRR,
    tax (which jurisdiction?).
11. **Performance.** Interpreter throughput is about 162k simple loop iterations/sec
    (`README.md` "ECS & particle engine"). Is that acceptable for heavy jobs (e.g. Monte
    Carlo retirement sims with 10k+ runs), or should those run in the Python host?

## Minor upstream issue noticed (not blocking)
`examples/stdlib_full_test.nova` failure path calls `len(state["checks"])`, but
`state["checks"]` is a number, so the report itself would error if any check failed.
