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
