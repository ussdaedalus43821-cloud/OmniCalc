"""Headless tests of the NovaLang <-> Python bridge (no Tkinter, no display).

Run: python3 -m unittest discover -s tests/host -p "*_test.py" -t .
"""

import ast
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from src.host import app, nova_runtime  # noqa: E402

CANONICAL = ("200,000.00", "6.5", "360", "0")
# CI runners are slower and noisier than a workstation; the workflow may
# raise this with OMNICALC_BUDGET_MS. Locally it is the real 100 ms budget.
BUDGET_MS = float(os.environ.get("OMNICALC_BUDGET_MS", app.BUDGET_MS))


def cli_result(*inputs):
    completed = subprocess.run(
        [sys.executable, nova_runtime.NOVA_SCRIPT, os.path.join(REPO_ROOT, "tools", "calc_cli.nova"), *inputs],
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    )
    return json.loads(completed.stdout)


class BridgeTest(unittest.TestCase):
    def test_host_result_matches_the_novalang_cli(self):
        for inputs in [CANONICAL, ("200000", "6.5", "360", "105.34"), ("15,000", "0", "12", "")]:
            with self.subTest(inputs=inputs):
                self.assertEqual(app.calculate(*inputs), cli_result(*inputs))

    def test_canonical_values_arrive_unchanged(self):
        result = app.calculate(*CANONICAL)
        self.assertEqual(result["payment"], 126414)
        self.assertEqual(result["total_interest"], 25508582)
        self.assertEqual(result["payoff_period"], 360)
        self.assertEqual(result["rows"][359], [360, 125956, 679, 125277, 0, 0, -458])
        self.assertEqual(app.format_minor(result["payment"], result["scale"]), "1,264.14")

    def test_calculate_is_within_the_ui_budget(self):
        app.calculate(*CANONICAL)
        timings = []
        for _ in range(3):
            start = time.perf_counter()
            app.calculate(*CANONICAL)
            timings.append(app.elapsed_ms(start))
        print("\ncalculate (payment + schedule + IRR): best {:.1f} ms of {}".format(min(timings), [round(t, 1) for t in timings]), file=sys.stderr)
        self.assertLess(min(timings), BUDGET_MS)

    def test_invalid_input_is_a_clean_calculation_error(self):
        with self.assertRaises(app.CalculationError) as caught:
            app.calculate("abc", "6.5", "360", "0")
        self.assertEqual(str(caught.exception), 'parse: principal "abc" is not a number')

    def test_missing_vendor_fails_with_a_specific_message(self):
        missing = os.path.join(REPO_ROOT, "vendor", "does-not-exist")
        with mock.patch.object(nova_runtime, "NOVA_DIR", missing), \
                mock.patch.object(nova_runtime, "NOVA_SCRIPT", os.path.join(missing, "novalang.py")):
            with self.assertRaises(nova_runtime.NovaPinError) as caught:
                app.load_engine(fresh=True)
        self.assertIn("NovaLang not found at", str(caught.exception))
        self.assertIn("git submodule update --init", str(caught.exception))
        app.load_engine(fresh=True)

    def test_app_py_does_no_arithmetic_outside_formatting(self):
        """The bridge contract, enforced: arithmetic operators may only appear
        in the functions app.ARITHMETIC_ALLOWED names."""
        with open(app.__file__, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        arithmetic = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
        offenders = []
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.Lambda)) or getattr(function, "name", "") in app.ARITHMETIC_ALLOWED:
                continue
            for node in ast.walk(function):
                if isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, arithmetic):
                    if isinstance(node.op, ast.Add) and is_string_concatenation(node):
                        continue
                    offenders.append("{} line {}".format(getattr(function, "name", "lambda"), node.lineno))
        self.assertEqual(offenders, [], "arithmetic in the host breaks the bridge contract")


def is_string_concatenation(node):
    """`"text" + x` or `x + "text"`, or [...] + [...]: building strings/lists, not math."""
    sides = [node.left, node.right] if isinstance(node, ast.BinOp) else [node.value]
    for side in sides:
        if isinstance(side, ast.Constant) and isinstance(side.value, str):
            return True
        if isinstance(side, (ast.List, ast.JoinedStr)):
            return True
        if isinstance(side, ast.Call) and getattr(side.func, "id", "") == "str":
            return True
        if isinstance(side, ast.BinOp) and is_string_concatenation(side):
            return True
    return False


if __name__ == "__main__":
    unittest.main()
