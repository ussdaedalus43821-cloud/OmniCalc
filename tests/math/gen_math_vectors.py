#!/usr/bin/env python3
"""Reference vectors for the M8 math engine (docs/M8-MATH-DESIGN.md).

Run `python3 tests/math/gen_math_vectors.py` to regenerate:
  tests/math/vectors/scientific.json  - expression cases for src/math/scientific.nova
  tests/math/vectors/units.json       - conversion cases for src/math/units.nova

Independence:
- **Expressions.** Every case is written twice: once as the text the NovaLang evaluator parses,
  and once as a Python expression (fractions.Fraction for exact values, the math module for
  floats). The reference never parses the text, so a parser bug can't hide behind a matching
  reference.
- **Display.** It's computed from the exact value: Fraction for exact values, and
  Decimal(float), the float's exact binary value, for floats. Rounding is half-up to 12
  significant figures, following the design's rules.
- **Units.** Every factor is re-derived here from its definition (international inch and pound,
  gallon = 231 in^3, lbf = lb * 9.80665, ...), never read from src/math/units.json. The script
  first checks that units.json agrees with these derivations, unit by unit, and fails if it
  doesn't.

Cases that must fail record an "error" fragment that the NovaLang message must contain.
"""

import json
import math
import os
from decimal import ROUND_HALF_UP, Decimal, getcontext
from fractions import Fraction as F

getcontext().prec = 60
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DIGITS = 12


# ---------------------------------------------------------------- display (the design's rules)

def _round_sig(d, digits):
    """Decimal d (non-zero) rounded half-up to `digits` significant figures -> (digit string, exponent)."""
    exponent = d.adjusted()                       # position of the leading digit
    quantum = Decimal(1).scaleb(exponent - digits + 1)
    q = d.quantize(quantum, rounding=ROUND_HALF_UP)
    if q.adjusted() != exponent:                  # 9.99... rounded up to 10.0...
        exponent = q.adjusted()
        q = d.quantize(Decimal(1).scaleb(exponent - digits + 1), rounding=ROUND_HALF_UP)
    return q, exponent


def _plain(q):
    text = format(q, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _scientific(q, exponent):
    mantissa = q.scaleb(-exponent)
    text = _plain(mantissa)
    return "{}e{}{:02d}".format(text, "+" if exponent >= 0 else "-", abs(exponent))


def terminates_within(f, digits):
    """True if Fraction f has a terminating decimal with at most `digits` decimals."""
    d = f.denominator
    twos = fives = 0
    while d % 2 == 0:
        d //= 2
        twos += 1
    while d % 5 == 0:
        d //= 5
        fives += 1
    return d == 1 and max(twos, fives) <= digits


def display_exact(f):
    if f.denominator == 1:
        return str(f.numerator)
    if terminates_within(f, DIGITS):
        return _plain(Decimal(f.numerator) / Decimal(f.denominator))
    return display_decimal(Decimal(f.numerator) / Decimal(f.denominator))


def display_decimal(d):
    if d == 0:
        return "0"
    q, exponent = _round_sig(d, DIGITS)
    if exponent >= 12 or exponent <= -7:
        return _scientific(q, exponent)
    return _plain(q)


def display_float(x):
    assert math.isfinite(x)
    return display_decimal(Decimal(x))           # Decimal(x) is the float's exact binary value


def exact_text(f):
    return "" if f.denominator == 1 else "{}/{}".format(f.numerator, f.denominator)


# ---------------------------------------------------------------- expression cases

def exact_case(text, value, note=""):
    value = F(value)
    return {"text": text, "angle": "rad", "kind": "exact", "num": value.numerator, "den": value.denominator,
            "display": display_exact(value), "exact_text": exact_text(value), "note": note}


def float_case(text, value, angle="rad", note=""):
    return {"text": text, "angle": angle, "kind": "float", "value": repr(float(value)),
            "display": display_float(float(value)), "note": note}


def error_case(text, fragment, note=""):
    return {"text": text, "angle": "rad", "error": fragment, "note": note}


def deg(x):
    return math.radians(x)


def scientific_cases():
    c = []
    # -- grammar and precedence (each fixes a convention the design names)
    c.append(exact_case("3 + 4 * (2 - 1)", 3 + 4 * (2 - 1), "the brief's example"))
    c.append(exact_case("2 + 3 * 4", 14, "* binds tighter than +"))
    c.append(exact_case("(2 + 3) * 4", 20))
    c.append(exact_case("10 - 4 - 3", 3, "left-associative -"))
    c.append(exact_case("100 / 10 / 5", 2, "left-associative /"))
    c.append(exact_case("-2^2", -4, "unary minus binds looser than ^ (maths convention)"))
    c.append(exact_case("(-2)^2", 4))
    c.append(exact_case("2^-1", F(1, 2), "signed exponent"))
    c.append(exact_case("2^3^2", 512, "^ is right-associative"))
    c.append(exact_case("3!^2", 36, "postfix ! binds tighter than ^"))
    c.append(exact_case("-3!", -6))
    c.append(exact_case("--5", 5, "repeated unary minus"))
    c.append(exact_case("+7", 7))
    c.append(exact_case("  1+2  ", 3, "whitespace ignored"))
    c.append(exact_case("2 × 3 ÷ 4 − 1", F(1, 2), "unicode operator aliases"))
    c.append(exact_case("3²", 9, "superscript square"))
    c.append(exact_case("2³", 8, "superscript cube"))
    # -- exact arithmetic
    c.append(exact_case("0.1 + 0.2", F(3, 10), "decimal literals are exact: 0.3, not 0.30000000000000004"))
    c.append(exact_case("1/3", F(1, 3), "non-terminating: rounded display + exact 1/3"))
    c.append(exact_case("2/3", F(2, 3), "half-up at the 12th figure: ...667"))
    c.append(exact_case("1/8", F(1, 8), "terminating decimal shown exactly"))
    c.append(exact_case("1/3 + 1/6", F(1, 2)))
    c.append(exact_case("1.5e-3", F(3, 2000), "exponent notation, exact"))
    c.append(exact_case("2e3 + .5", F(4001, 2), "2e3 and a leading-dot literal"))
    c.append(exact_case("123456789 * 987654321", 123456789 * 987654321, "big integers stay exact"))
    c.append(exact_case("2^100", 2 ** 100, "exact integer power, 31 digits, shown in full"))
    c.append(exact_case("(2/3)^3", F(8, 27)))
    c.append(exact_case("(1/2)^-3", 8))
    c.append(exact_case("8^(1/3)", 2, "exact rational root"))
    c.append(exact_case("(-8)^(1/3)", -2, "odd root of a negative base"))
    c.append(exact_case("(9/4)^(1/2)", F(3, 2)))
    c.append(exact_case("16^(3/4)", 8))
    c.append(exact_case("sqrt(144)", 12, "perfect square stays exact"))
    c.append(exact_case("sqrt(2.25)", F(3, 2)))
    c.append(exact_case("root(1000, 3)", 10))
    c.append(exact_case("10!", math.factorial(10)))
    c.append(exact_case("0!", 1))
    c.append(exact_case("25!", math.factorial(25), "26 digits, exact"))
    c.append(exact_case("ncr(52, 5)", math.comb(52, 5)))
    c.append(exact_case("npr(10, 3)", math.perm(10, 3)))
    c.append(exact_case("gcd(462, 1071)", math.gcd(462, 1071)))
    c.append(exact_case("lcm(4, 6)", 12))
    c.append(exact_case("abs(-7/2)", F(7, 2)))
    c.append(exact_case("floor(-7/2)", -4))
    c.append(exact_case("ceil(-7/2)", -3))
    c.append(exact_case("round(2.5)", 3, "half-up, the house rule (not banker's)"))
    c.append(exact_case("round(-2.5)", -3, "halves away from zero"))
    c.append(exact_case("round(3.14159, 2)", F(314, 100)))
    c.append(exact_case("mod(-7, 3)", 2, "floored modulo: sign of the divisor"))
    c.append(exact_case("mod(7, -3)", -2))
    c.append(exact_case("min(3, 1/2, 2)", F(1, 2)))
    c.append(exact_case("max(-1, -1/3)", F(-1, 3)))
    c.append(exact_case("1/3 * 3", 1, "exact rationals cancel"))
    # -- floats (transcendentals, irrational roots, constants)
    c.append(float_case("sqrt(2)", math.sqrt(2), note="not a perfect square: float"))
    c.append(float_case("2^0.5", 2 ** 0.5, note="irrational power: float"))
    c.append(float_case("pi", math.pi))
    c.append(float_case("e", math.e))
    c.append(float_case("2 * pi", 2 * math.pi))
    c.append(float_case("sin(pi / 6)", math.sin(math.pi / 6), note="0.49999999999999994, displays 0.5"))
    c.append(float_case("cos(0)", math.cos(0)))
    c.append(float_case("tan(1)", math.tan(1)))
    c.append(float_case("sin(30)", math.sin(deg(30)), angle="deg", note="degree mode"))
    c.append(float_case("cos(60)", math.cos(deg(60)), angle="deg"))
    c.append(float_case("tan(45)", math.tan(deg(45)), angle="deg"))
    c.append(float_case("atan(1)", math.atan(1), note="NovaLang has no atan built-in"))
    c.append(float_case("atan(1)", math.degrees(math.atan(1)), angle="deg", note="inverse trig returns degrees in deg mode"))
    c.append(float_case("asin(0.5)", math.asin(0.5)))
    c.append(float_case("acos(-1)", math.acos(-1)))
    c.append(float_case("atan(1e6)", math.atan(1e6), note="argument reduction for large x"))
    c.append(float_case("atan(-0.3)", math.atan(-0.3)))
    c.append(float_case("atan2(-1, -1)", math.atan2(-1, -1), note="quadrant-aware"))
    c.append(float_case("exp(1)", math.exp(1), note="NovaLang has no exp built-in"))
    c.append(float_case("exp(-2.5)", math.exp(-2.5)))
    c.append(float_case("ln(10)", math.log(10)))
    c.append(float_case("log10(2)", math.log10(2)))
    c.append(float_case("log2(10)", math.log2(10)))
    c.append(float_case("log(8, 2)", math.log(8, 2), note="our log(x, base), never NovaLang's logger"))
    c.append(float_case("sinh(1)", math.sinh(1)))
    c.append(float_case("cosh(1)", math.cosh(1)))
    c.append(float_case("tanh(0.5)", math.tanh(0.5)))
    c.append(float_case("1 / 3 + pi", 1 / 3 + math.pi, note="exact + float -> float"))
    c.append(float_case("2^100 * 1.0 * pi", 2 ** 100 * math.pi, note="large: scientific notation"))
    c.append(float_case("exp(-20)", math.exp(-20), note="small: scientific notation"))
    c.append(float_case("1e-3 * pi", 1e-3 * math.pi, note="0.00314... stays plain (exponent -3)"))
    # -- errors
    c.append(error_case("1 / 0", "division by zero"))
    c.append(error_case("1 / (2 - 2)", "division by zero"))
    c.append(error_case("sqrt(-1)", "not a real number"))
    c.append(error_case("(-8)^(1/2)", "not a real number"))
    c.append(error_case("0^-1", "division by zero"))
    c.append(error_case("ln(0)", "ln needs a number greater than zero"))
    c.append(error_case("asin(2)", "asin needs a number from -1 to 1"))
    c.append(error_case("1001!", "factorial needs a whole number from 0 to 1000"))
    c.append(error_case("2.5!", "factorial needs a whole number from 0 to 1000"))
    c.append(error_case("3 +", "unexpected end"))
    c.append(error_case("(1 + 2", "missing \")\""))
    c.append(error_case("1 + 2)", "unexpected \")\" at position 5"))
    c.append(error_case("2 pi", "missing operator"))
    c.append(error_case("2(3)", "missing operator"))
    c.append(error_case("sine(1)", "unknown function \"sine\" at position 0"))
    c.append(error_case("foo + 1", "unknown name \"foo\" at position 0"))
    c.append(error_case("sqrt(1, 2)", "sqrt takes 1 argument, got 2"))
    c.append(error_case("1 $ 2", "unexpected character \"$\" at position 2"))
    c.append(error_case("", "enter an expression"))
    c.append(error_case("1" + "+1" * 300, "at most 500 characters"))
    c.append(error_case("exp(1000)", "not a finite number", "float overflow is an error, not inf"))
    return c


# ---------------------------------------------------------------- units

def derived_factors():
    """Every unit's factor to its category's base unit, from definitions - not from units.json."""
    inch = F("0.0254")
    ft, yd, mi, nmi = 12 * inch, 36 * inch, 5280 * 12 * inch, F(1852)
    lb, g0 = F("0.45359237"), F("9.80665")
    lbf = lb * g0
    gal = 231 * inch ** 3
    qt, pt = gal / 4, gal / 8
    cup = pt / 2
    floz = cup / 8
    tbsp = floz / 2
    tsp = tbsp / 3
    return {
        "m": 1, "km": 1000, "cm": F(1, 100), "mm": F(1, 1000), "um": F(1, 10 ** 6), "nm": F(1, 10 ** 9),
        "in": inch, "ft": ft, "yd": yd, "mi": mi, "nmi": nmi,
        "m2": 1, "km2": 10 ** 6, "cm2": F(1, 10 ** 4), "ha": 10 ** 4, "acre": 43560 * ft ** 2,
        "ft2": ft ** 2, "in2": inch ** 2, "mi2": mi ** 2,
        "m3": 1, "L": F(1, 1000), "mL": F(1, 10 ** 6), "cm3": F(1, 10 ** 6), "gal": gal, "qt": qt, "pt": pt,
        "cup": cup, "floz": floz, "tbsp": tbsp, "tsp": tsp, "ft3": ft ** 3, "in3": inch ** 3,
        "impgal": F("0.00454609"),
        "kg": 1, "g": F(1, 1000), "mg": F(1, 10 ** 6), "t": 1000, "lb": lb, "oz": lb / 16, "st": 14 * lb,
        "ton": 2000 * lb,
        "s": 1, "ms": F(1, 1000), "min": 60, "h": 3600, "day": 86400, "week": 7 * 86400,
        "m/s": 1, "km/h": F(1000, 3600), "mph": mi / 3600, "kn": nmi / 3600, "ft/s": ft,
        "K": 1, "degC": 1, "degF": F(5, 9), "degR": F(5, 9),
        "Pa": 1, "kPa": 1000, "bar": 10 ** 5, "atm": 101325, "psi": lbf / inch ** 2, "torr": F(101325, 760),
        "mmHg": F("133.322387415"),
        "J": 1, "kJ": 1000, "cal": F("4.184"), "kcal": 4184, "Wh": 3600, "kWh": 3600 * 1000,
        "BTU": F("1055.05585262"), "eV": F("1.602176634e-19"),
        "W": 1, "kW": 1000, "hp": 550 * ft * lbf,
        "bit": F(1, 8), "B": 1, "kB": 10 ** 3, "MB": 10 ** 6, "GB": 10 ** 9, "TB": 10 ** 12,
        "KiB": 2 ** 10, "MiB": 2 ** 20, "GiB": 2 ** 30, "TiB": 2 ** 40,
    }


OFFSETS = {"K": 0, "degC": F("273.15"), "degF": F("459.67"), "degR": 0}


def parse_factor(text):
    if "/" in text:
        top, bottom = text.split("/")
        return F(int(top), int(bottom))
    return F(Decimal(text))


def check_table(table):
    derived = derived_factors()
    seen = set()
    for unit in table["units"]:
        symbol = unit["symbol"]
        for name in [symbol] + unit.get("aliases", []):
            assert name not in seen, "duplicate symbol or alias: " + name
            seen.add(name)
        assert unit["category"] in table["categories"], "unknown category for " + symbol
        assert symbol in derived, "no independent derivation for " + symbol
        assert parse_factor(unit["factor"]) == F(derived[symbol]), "factor mismatch for " + symbol
        if "offset" in unit:
            assert unit["category"] == "temperature", "offset outside temperature: " + symbol
            assert parse_factor(unit["offset"]) == F(OFFSETS[symbol]), "offset mismatch for " + symbol
    assert set(derived) == {u["symbol"] for u in table["units"]}, "derivations and table list different units"


def to_base(symbol, x, factors):
    return (x + OFFSETS.get(symbol, 0)) * factors[symbol]


def from_base(symbol, base, factors):
    return base / factors[symbol] - OFFSETS.get(symbol, 0)


def convert(x, src, dst, factors):
    return from_base(dst, to_base(src, F(x), factors), factors)


def units_cases():
    factors = {k: F(v) for k, v in derived_factors().items()}
    cases = []

    def case(text, src, dst, note=""):
        value = convert(F(Decimal(text)), src, dst, factors)
        cases.append({"value": text, "from": src, "to": dst, "num": value.numerator, "den": value.denominator,
                      "display": display_exact(value), "exact_text": exact_text(value), "note": note})

    case("1", "ft", "in", "exactly 12")
    case("1", "mi", "km", "exactly 1.609344")
    case("100", "km/h", "mph")
    case("26.2", "mi", "km", "marathon")
    case("1", "acre", "m2", "exactly 4046.8564224")
    case("1", "gal", "L", "exactly 3.785411784")
    case("1", "cup", "mL", "non-terminating US cup")
    case("2", "tbsp", "tsp", "exactly 6")
    case("1", "impgal", "gal")
    case("150", "lb", "kg")
    case("1", "st", "lb", "exactly 14")
    case("1", "kg", "oz")
    case("98.6", "degF", "degC", "body temperature: exactly 37")
    case("-40", "degC", "degF", "where the scales meet")
    case("0", "K", "degC", "exactly -273.15")
    case("100", "degC", "degR")
    case("32", "psi", "kPa", "tyre pressure")
    case("1", "atm", "torr", "exactly 760")
    case("1", "atm", "psi")
    case("1", "kWh", "BTU")
    case("2000", "kcal", "kJ")
    case("1", "hp", "kW")
    case("1", "GiB", "GB", "binary vs decimal prefix")
    case("1", "B", "bit", "exactly 8")
    case("1", "day", "s", "exactly 86400")
    case("90", "min", "h", "exactly 1.5")
    case("1", "kn", "km/h", "exactly 1.852")
    case("1", "eV", "J", "SI 2019, exact")
    case("0.5", "ft2", "in2", "exactly 72")
    case("1", "m3", "ft3")
    errors = [
        {"value": "1", "from": "ft", "to": "kg", "error": "cannot convert length (ft) to mass (kg)"},
        {"value": "1", "from": "fts", "to": "m", "error": "unknown unit \"fts\""},
        {"value": "1", "from": "MM", "to": "m", "error": "unknown unit \"MM\"", "note": "symbols are case-sensitive"},
        {"value": "abc", "from": "m", "to": "ft", "error": "is not a number"},
    ]
    return cases, errors


# ---------------------------------------------------------------- write

def main():
    table = json.load(open(os.path.join(ROOT, "src", "math", "units.json"), encoding="utf-8"))
    check_table(table)
    sci = scientific_cases()
    conversions, unit_errors = units_cases()
    os.makedirs(os.path.join(HERE, "vectors"), exist_ok=True)
    with open(os.path.join(HERE, "vectors", "scientific.json"), "w", encoding="utf-8") as handle:
        json.dump({"digits": DIGITS, "cases": sci}, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    with open(os.path.join(HERE, "vectors", "units.json"), "w", encoding="utf-8") as handle:
        json.dump({"cases": conversions, "errors": unit_errors}, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    kinds = {}
    for c in sci:
        kinds[c.get("kind", "error")] = kinds.get(c.get("kind", "error"), 0) + 1
    print("units.json: {} units agree with independent derivations".format(len(table["units"])))
    print("scientific.json: {} cases {}".format(len(sci), kinds))
    print("units vectors: {} conversions, {} error cases".format(len(conversions), len(unit_errors)))


if __name__ == "__main__":
    main()
