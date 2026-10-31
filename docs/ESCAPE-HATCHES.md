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
- Measured: 10 solves each, Python 3.13, direct interpreter (not `--bootstrap`). Re-measured in
  M2: the M1 figures came from loops written as `for i = 0 to 10`, and NovaLang's `to` is
  inclusive, so those loops ran 11 times and overstated each solve by about 10%.

  | Case | Per solve |
  |---|---|
  | 360 periods @ 6.5% | 5.4 ms |
  | 480 @ 24% | 7.4 ms |
  | 1,200 @ 3% | 14.4 ms |
  | 12 @ 0.5% | 3.0 ms |

  For comparison, `pmt` takes about 0.6–0.9 ms per call.
- Why it's fast: bisection takes about 40–50 iterations. Each iteration is two exact
  `pow()` calls on Python ints, so the step count stays low even though the ints have
  thousands of digits.
- Precision: exact rational residual. The result is within 1e-12 per period, and it is
  checked by re-deriving pmt/fv to within one minor unit.
- Decision: well under the 100 ms budget, with no precision gain from moving it to
  Python. It stays in NovaLang.

### Amortization schedule — `src/finance/amortization.nova` (M2, 2026-10-31)
- Measured: 10 schedules each, same setup as above.

  | Case | Per schedule |
  |---|---|
  | 360 monthly rows | 33.5 ms |
  | 628 biweekly rows | 54.9 ms |
  | 780 rows (the biweekly maximum for a 30-year term) | 57.5 ms |

- How it stays fast: the loop works on plain ints. It uses `money.round_half_up_whole`, the
  unchecked form of the one rounding rule, because the checks in `round_half_up` alone cost
  about 53 ms over 628 rows.
- Decision: within the 100 ms budget, so it stays in NovaLang. Re-measure before adding
  longer schedules (e.g. weekly) or per-row features, because cost grows linearly with rows.

## Known approximations

Behavior that is deliberately not exact. Each entry says what is approximated, why, and what to
use when exactness matters.

### `tvm.n` → `periods` slack (M1, documented in M2)
- **What.** `tvm.n` returns `{exact, periods}`. `periods` follows `tvm.whole_periods`: let
  `f = floor(exact)`; if `exact − f < 1e-4`, report `f`, otherwise `f + 1` (never below 1).
- **Why.** A target rounded to a minor unit pushes `exact` just past a whole number. The 120-month
  savings plan whose fv was rounded to the cent solves to `exact = 120.0000125`; plain
  `ceil()` would report 121 months.
- **What's approximate.** The honest answer is still 120.0000125. `periods = 120` is a
  display convenience, not a mathematical truth. **Financial logic must use `exact`**; no module
  may make decisions from `periods`.
- **Better alternative, deferred.** Snap only when the overshoot can be attributed to the
  rounding of fv/pv: compare the overshoot with the period fraction that one minor unit of the
  target is worth. It's more work and not needed yet.
- **Pinned by tests.** `tests/finance/tvm_test.nova` checks the boundary: 120.00005 → 120,
  120.0002 → 121.
