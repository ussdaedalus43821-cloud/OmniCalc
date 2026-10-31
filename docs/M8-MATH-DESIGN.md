# M8 — Math engine: API proposal (for review before implementation)

Status: **API approved**:
- `scientific.nova` is **implemented and green** (112 checks against the generator's vectors);
- `units.nova` and `datetime.nova` are next;
- the data file is `src/math/units.json`. The Python reference generator `tests/math/gen_math_vectors.py` already
encodes the semantics below, so reviewing this document and the generated vectors together is
reviewing the behavior.

## What was measured first ("profile before writing a screen")
- **Built-ins we have:** `sin cos tan ln log10 sqrt pow abs floor ceil`, `PI`, `E`.
- **Built-ins we don't have:** `exp`, `asin`, `acos`, `atan`, and the hyperbolics. They're
  written in NovaLang (below).
- **`log` is not a logarithm.** It's the stderr logger (`novalang.py` `builtin_log`), so a
  stray `log(8, 2)` *prints* instead of failing. The evaluator's `log` name maps to our own
  function, never to the built-in.
- **No scientific notation:** NovaLang source can't write `1e3`, and `num()` rejects `"1e3"`.
  The tokenizer reads exponents itself.
- **`str(float)` is unusable for display:** `str(pow(10.0, 25))` is
  `"10000000000000000905969664"`. Display formatting is ours (below).
- **Cost of the obvious design:** a char-by-char tokenizer plus recursive-descent evaluation of a
  95-character expression in exact rationals takes **2.4 ms** (15 characters: 0.5 ms). The parser
  isn't the budget risk. The risks are the series-based functions, display formatting and loading
  the units table, and each gets profiled as it lands.

## `src/math/scientific.nova`

### Values
A value is one of:
- `{kind: "exact", num, den}`: a reduced rational, `den > 0`. Integers have `den = 1`.
- `{kind: "float", value}`: a finite binary float. Non-finite results are errors, never values.

**Exactness rules** (the core promise: exact whenever exact is possible):

| Input or operation | Result |
|---|---|
| A literal | exact. `0.1` is 1/10 and `1.5e-3` is 3/2000, so `0.1 + 0.2 = 0.3` exactly. |
| `+ - * /` on exact values | exact. Any float operand makes the result float. |
| Division by zero | error |
| `x ^ n`, exact `x`, integer `n` (`|n|` ≤ 4096, result ≤ 100,000 digits) | exact; otherwise float |
| `x ^ (p/q)`, exact `x` (`q` ≤ 64) | exact when `x` has an exact `q`-th root: `8^(1/3) = 2`, `(-8)^(1/3) = -2`, `(9/4)^(1/2) = 3/2`. Otherwise float. A negative base with even `q` is an error ("not a real number"). |
| `0 ^ negative` | error |
| `sqrt(x)`, `root(x, n)` | exact for perfect powers (integer square root by Newton on ints); otherwise float. `sqrt(negative)` is an error. |
| `n!` | exact, for integers 0 ≤ n ≤ 1000; otherwise an error |
| `nCr`, `nPr`, `gcd`, `lcm` | exact, integers only |
| `abs`, `floor`, `ceil` | exact in, exact out |
| `round(x)` | half-up (away from zero), the house rule; `round(x, d)` rounds to `d` decimals |
| `mod(a, b)` | floored modulo: the result has `b`'s sign, like NovaLang's `%` |
| `min(...)`, `max(...)` | variadic; exact if every argument is exact |
| Transcendentals (`sin cos tan asin acos atan atan2 sinh cosh tanh exp ln log10 log2 log`) | always float |
| Constants `pi`, `e` | float |

### Trig and angle mode
`options.angle` is `"rad"` (default) or `"deg"`. In degrees, inputs to `sin`/`cos`/`tan` are
converted, and outputs of `asin`/`acos`/`atan`/`atan2` are converted back.

### Functions written in NovaLang
NovaLang lacks these, so they're implemented here (the generator checks them against Python's
`math` module at a relative 1e-14):
- `exp(x) = pow(E, x)`;
- `atan`: argument reduction to |x| ≤ tan(π/12), then its Taylor series;
- `asin(x) = atan(x / sqrt((1 − x)(1 + x)))` (the factored form loses less near ±1), and
  `acos = π/2 − asin`;
- `atan` for |x| > 1 uses `π/2 − atan(1/x)`, and for x in (tan 15°, 1] uses
  `π/6 + atan((x√3 − 1)/(√3 + x))`. The series then only sees |y| ≤ 0.268;
- hyperbolics from `exp`.

### Display
`display(value, digits = 12) → text`, and `exact_text(value)`, which is `"num/den"` for a
non-integer rational.
- **Exact integer:** all its digits, `"-1234567"`. No grouping: grouping is a host display
  choice.
- **Exact rational with a terminating decimal of ≤ `digits` decimals:** shown exactly
  (`"0.125"`). Otherwise rounded half-up to `digits` significant figures (`"0.333333333333"`),
  with `exact_text` `"1/3"` shown beside it.
- **Float:** first converted to its *exact* binary rational. Repeated doubling is exact in binary
  floating point, so this takes at most a few dozen steps. It's then rounded half-up to `digits`
  significant figures with exact integer arithmetic, and trailing zeros are trimmed. Scientific
  notation `"1.23456789012e+25"` is used when the decimal exponent is ≥ 12 or ≤ −7.
- This matches Python's `Decimal(float)` digit for digit, which is why it's testable exactly.
- **Why NovaLang does this:** the bridge contract (no arithmetic in the host). The host shows the
  text.

### Tokenizer — `tokenize(text) → [{kind, text, at}]`
- **Kinds:** `number`, `name`, `op`, plus a final `end`. `at` is the 0-based character position,
  used in error messages.
- **`number`:** `digits [. digits] [e [+|-] digits]`, or `. digits`. An `e` is an exponent only
  when digits follow it, so `2e3` is 2000. A bare `2e` is a number followed by the name `e`, which
  then fails as "missing operator" (implicit multiplication is not supported).
- **`name`:** `[a-z][a-z0-9]*`, case-insensitive (lower-cased).
- **`op`:** `+ - * / ^ ( ) , !`. Unicode aliases are normalized while tokenizing: `×` → `*`,
  `÷` → `/`, `−` → `-`, `π` → `pi`, `²` → `^2`, `³` → `^3`.
- Whitespace is ignored. The maximum length is 500 characters.
- Anything else is an error: `math: unexpected character "$" at position 4`.

### Grammar (recursive descent) — `parse(tokens) → AST`
```
expression := sum END
sum        := product (("+" | "-") product)*
product    := unary (("*" | "/") unary)*
unary      := ("-" | "+") unary | power
power      := postfix ("^" unary)?        # right-associative: 2^3^2 = 2^9
postfix    := primary "!"*
primary    := NUMBER | NAME | NAME "(" args ")" | "(" sum ")"
args       := sum ("," sum)*
```
- **Conventions this fixes**, each pinned by a test:
  - `-2^2 = -4` (unary minus binds looser than `^`, the standard maths convention; Excel
    differs);
  - `2^-1 = 1/2`;
  - `2^3^2 = 512`;
  - `3!^2 = 36`;
  - `-3! = -6`.
- **AST nodes:**
  - `{node: "num", value}`;
  - `{node: "name", name, at}`;
  - `{node: "neg", arg}`;
  - `{node: "bin", op, left, right}`;
  - `{node: "call", name, args, at}`;
  - `{node: "fact", arg}`.
- **Errors carry a position:** `math: missing ")" at position 9`,
  `math: unknown function "sine" at position 0`, `math: sqrt takes 1 argument, got 2`.
- **No implicit multiplication** (`2pi`, `2(3)`). It's ambiguous next to function calls, so
  it's an explicit error: "missing operator".

### Evaluation and public surface
```
evaluate(text, options) -> {value, display, exact_text}   # options: {angle, digits}
tokenize(text)          -> tokens
parse(tokens)           -> ast
eval_ast(ast, options)  -> value
display(value, digits)  -> text
exact(num, den)         -> value        # helpers other modules can use
to_float(value)         -> float
isqrt(n)                -> int           # floor(sqrt(n)) for int n >= 0, exact
```
- If the evaluator ever crowds the 70 ms budget, `tokenize`/`parse` become the checked wrappers
  and the evaluator gets an unchecked core over a pre-validated AST. The measurement above says it
  won't be needed for anything a person types.

## `src/math/units.nova`

### The table (`src/math/units.json`, checked in)
- `categories` maps each category to its base unit. There are 11 categories: length, area,
  volume, mass, time, speed, temperature, pressure, energy, power, data.
- `units`: 84 entries of `{symbol, name, category, factor, offset?, aliases?, source?}`.
- **`factor`** converts one unit to the category's base unit. It's an exact decimal string
  (`"0.3048"`, `"1.602176634e-19"`) or exact `"num/den"`, for the six non-terminating ones (psi,
  torr, km/h, US cup/fl oz/tsp…).
- **Every factor is exact by definition:**
  - international inch 0.0254 m and pound 0.45359237 kg (1959);
  - US gallon = 231 in³;
  - lbf = lb × 9.80665;
  - eV per SI 2019, and so on.
  The generator re-derives every one independently, from those definitions rather than from this
  file, and fails on any mismatch.
- **Temperature is affine:** `kelvin = (x + offset) × factor`. For °F the factor is 5/9 and the
  offset 459.67. Only temperature may have an offset.
- **File I/O stays in the host** (the boundary table). The host reads `units.json` as text, and
  the façade passes that text to `units.load`. `json.loads` is one built-in call, and validation
  will be profiled.

### API
```
load(json_text)                       -> table   # validates: unique symbols+aliases, known
                                                  #   categories, factors parse as exact positive
                                                  #   rationals, offsets only for temperature
find(table, symbol_or_alias)          -> unit    # case-sensitive (mm != Mm, b = bit, B = byte)
convert(table, value, from, to)       -> exact   # value: exact rational; result exact {num, den}
convert_text(table, text, from, to)   -> {value, display, exact_text}  # parses text exactly
units_in(table, category)             -> [symbol]  # for the UI's drop-downs, table order
categories(table)                     -> [category]
```
- **Conversions are exact rational arithmetic:** `x × f_from / f_to` (temperature:
  `(x + o_from) × f_from / f_to − o_to`). The only rounding is at display, through
  `scientific.display`, so `1 ft → in` is exactly 12 and `1 mi → km` is exactly 1.609344.
- **Errors:** an unknown unit gives `units: unknown unit "fts" (did you mean "ft"?)`, where the
  suggestion comes from a case-insensitive prefix match. A cross-category conversion gives
  `units: cannot convert length (ft) to mass (kg)`.
- **Not in M8:** compound units (`kg·m/s²`), SI-prefix parsing (`km` is listed explicitly),
  currency.

## `src/math/datetime.nova` (sketch; detailed with its generator in the next step)
- **Calendar arithmetic:**
  - `add_duration(date, {years, months, days})`: months and years clamp to month-end, like
    `dates.add_months`; negative durations subtract.
  - `duration_between(a, b)`: calendar `{years, months, days}`.
- **Business days:**
  - `weekday(date)` (0 = Monday);
  - `is_business_day(date, holidays)`, `add_business_days(date, n, holidays)`,
    `business_days_between(a, b, holidays)` (counted over `(a, b]`).
  - `holidays` is a user-supplied list of serials, and weekends are Saturday and Sunday.
- **`day_count(start, end, convention)`** returns an exact `{num, den}` year fraction. The
  conventions are `"act/365f"` (exists), `"act/360"`, `"30/360us"` (bond basis), `"30e/360"`
  and `"act/act-isda"`. ISDA is exact, with denominators of 365 and 366.

## `src/app/math_screen.nova` and the Math tab
- **One façade call:** `calculate(expression, angle, value, from_unit, to_unit, units_json)`.
  It evaluates the expression and converts the value. An empty section gives "—" rather than an
  error, so one Calculate press serves both.
- **The host** gains a "Math" tab:
  - an expression box;
  - an angle-mode choice;
  - a value box with from/to unit inputs, whose options come from the façade, so the host never
    reads unit semantics.
  It does zero arithmetic, enforced by the existing guard.
- **Budget:** the standard 70 ms single-schedule target.

## Known limitations to record in `docs/ESCAPE-HATCHES.md` as they're confirmed
- **Missing built-ins** (`exp`/`atan`/`asin`/`acos`/hyperbolics), written here in NovaLang.
- **`log` is the logger, not a logarithm.**
- **No float formatting control**, so display is our own exact routine.
- **Float precision:** a binary double's ~15–17 digits bound every transcendental. Display uses
  12 significant figures so the last shown digit is reliable.
