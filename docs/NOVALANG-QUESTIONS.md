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

## Upstream issues (reported; do not patch the submodule)
`Nova_Lang/examples/stdlib_full_test.nova`: the failure-report branch calls `len(state["checks"])`
on a number, so the summary crashes if any check fails.
Filed as https://github.com/ussdaedalus43821-cloud/Nova_Lang/issues/2. OmniCalc is unaffected
because it uses its own `TESTS_OK` sentinel (`tools/check.nova`, `tools/run_tests.py`).

Second issue: `floor()`, `ceil()` and `round()` raise a raw Python `ValueError`/`OverflowError`
on NaN/inf. `try`/`catch` can't intercept it.
Filed as https://github.com/ussdaedalus43821-cloud/Nova_Lang/issues/3. OmniCalc works around it
with `src/core/numbers.nova`, which rejects non-finite values before calling `floor()`.

Third issue: `README.md` "Language syntax" says `for i = 0 to 10 { print(i) }` "counts 0..9", but
the bound is **inclusive**: `for i = 0 to 3` visits 0, 1, 2, 3 (verified, and `step`/`downto`
too). `range(n)` *is* exclusive. The issue suggests fixing the docs rather than the runtime.
Filed as https://github.com/ussdaedalus43821-cloud/Nova_Lang/issues/4. OmniCalc's rule is in
`CLAUDE.md` ("Known gaps and traps").

## Embedding findings (M4, no upstream issue needed)
- `Nova().load_file(path)` followed by `nova.call("fn", ...)` works for functions defined at the
  top of the loaded file (`export def` included). The file's relative imports resolve against
  its own directory (`novalang.py` `Nova.load_file`).
- `str(NovaLangError)` is already the bare message, e.g. `parse: principal "abc" is not a
  number`, with no source excerpt, so the host shows it as is.
- Arguments and results cross the bridge as copies (`to_nova_value` / `to_python_value`), as
  the README warns. The screen façade returns plain ints, strings and lists, so this is free.

## M5
No new upstream findings. Two reminders that cost a rename each: `split` is a built-in, so it can't
be a variable name, and neither can `values`. Both are already covered by the `CLAUDE.md` rule on
reserved names.

## M6
No new upstream issues. One useful verified behavior: a `def` nested inside a function can read the
enclosing function's locals (a closure). `debt_payoff.nova` uses it to pass comparators to its
stable sort. It's not mentioned in `Nova_Lang/README.md`, and it worked under both the direct and
`--bootstrap` interpreters.

## M7
No new upstream issues. `regex(pattern, text)` is `re.search(...) is not None`
(`novalang.py` `builtin_regex`), which makes it a cheap shape check. Use `\Z`, not `$`, to anchor
the end, because `$` also matches before a trailing newline. Two `CLAUDE.md` reserved names
(`num`, `values`) were tripped again in new code and caught at load time. Unrelated to NovaLang:
Microsoft's RRI page contradicts itself ("1.2%", "8 years") next to its own `=RRI(96,...)`
result of 0.0009933, which is the monthly rate the formula computes. The test uses the formula's
value.
