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

_None._

## Decisions to keep in NovaLang (no escape hatch)

These were checked against the budget and stay in NovaLang. Re-measure if inputs grow.

### TVM rate solve — `src/finance/tvm.nova :: rate` (M1, 2026-10-31)
- Measured: 10 solves each, Python 3.13, direct interpreter (not `--bootstrap`).

  | Case | Per solve |
  |---|---|
  | 360 periods @ 6.5% | 6.0 ms |
  | 480 @ 24% | 7.2 ms |
  | 1,200 @ 3% | 15.1 ms |
  | 12 @ 0.5% | 4.1 ms |

  For comparison, `pmt` takes about 0.6–0.8 ms per call.
- Why it's fast: bisection takes about 40–50 iterations. Each iteration is two exact
  `pow()` calls on Python ints, so the step count stays low even though the ints have
  thousands of digits.
- Precision: exact rational residual. The result is within 1e-12 per period, and it is
  checked by re-deriving pmt/fv to within one minor unit.
- Decision: well under the 100 ms budget, with no precision gain from moving it to
  Python. It stays in NovaLang.
