"""CSV export, headless: write the canonical schedule, parse it back with csv.

Run: python3 -m unittest discover -s tests/host -p "*_test.py" -t .
"""

import csv
import io
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from src.host import app  # noqa: E402


class CsvExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = app.calculate("amortization", "200,000.00", "6.5", "360", "0")
        buffer = io.StringIO()
        app.export_csv(cls.result, buffer)
        cls.text = buffer.getvalue()
        cls.rows = list(csv.reader(io.StringIO(cls.text)))

    def test_header_and_row_count(self):
        self.assertEqual(self.rows[0], ["period", "payment", "interest", "principal", "balance", "extra", "adjustment"])
        self.assertEqual(len(self.rows), 361)

    def test_two_known_values(self):
        self.assertEqual(self.rows[1][2], "1083.33")      # month 1 interest
        self.assertEqual(self.rows[360][1], "1259.56")    # final, adjusted payment
        self.assertEqual(self.rows[360][6], "-4.58")      # the adjustment itself

    def test_reparses_to_the_same_schedule(self):
        """Decimal text back to integer cents (the test may do arithmetic; the host may not)."""
        parsed = [[int(row[0])] + [int(value.replace(".", "")) for value in row[1:]] for row in self.rows[1:]]
        self.assertEqual(parsed, self.result["rows"])

    def test_no_thousands_separators_in_csv(self):
        self.assertNotIn(",", "".join(self.rows[1][1:]))
        self.assertEqual(self.rows[1][4], "199819.19")


class RefinanceCsvTest(unittest.TestCase):
    """One row per scenario (keep vs refinance), not one row per month."""

    @classmethod
    def setUpClass(cls):
        cls.result = app.calculate("refinance", "200,000.00", "6.5", "360", "1,264.14", "5.0", "360", "6,000")
        buffer = io.StringIO()
        app.export_csv(cls.result, buffer)
        cls.rows = list(csv.reader(io.StringIO(buffer.getvalue())))

    def test_header_and_one_row_per_scenario(self):
        self.assertEqual(self.rows[0], ["scenario", "monthly_payment", "total_paid", "total_interest", "payoff_month", "closing_costs"])
        self.assertEqual([row[0] for row in self.rows[1:]], ["Keep current loan", "Refinance"])

    def test_known_values(self):
        self.assertEqual(self.rows[2][1], "1073.64")     # the new payment
        self.assertEqual(self.rows[2][5], "6000.00")     # closing costs
        self.assertEqual(self.rows[1][4], "360")         # a count, not money

    def test_reparses_to_the_same_rows(self):
        kinds = self.result["column_kinds"]
        parsed = [[value if kind == "text" else int(value.replace(".", "")) for value, kind in zip(row, kinds)] for row in self.rows[1:]]
        self.assertEqual(parsed, self.result["rows"])


class SavingsCsvTest(unittest.TestCase):
    def test_one_row_per_year(self):
        result = app.calculate("savings", "fv", "10,000.00", "500", "7", "30", "")
        buffer = io.StringIO()
        app.export_csv(result, buffer)
        rows = list(csv.reader(io.StringIO(buffer.getvalue())))
        self.assertEqual(rows[0], ["year", "contributed", "interest_earned", "balance"])
        self.assertEqual(len(rows), 31)
        self.assertEqual(rows[30][3], "691150.47")


class DebtPayoffCsvTest(unittest.TestCase):
    def test_per_debt_rows(self):
        result = app.calculate("debt_payoff", [["Medical", "1,200", "0", "50"], ["Card", "6,000", "24.99", "150"], ["Car", "9,000", "7", "250"]], "700", "avalanche")
        buffer = io.StringIO()
        app.export_csv(result, buffer)
        rows = list(csv.reader(io.StringIO(buffer.getvalue())))
        self.assertEqual(rows[0], ["order", "debt", "balance", "apr", "minimum", "paid_off_month", "interest_paid"])
        self.assertEqual(rows[1], ["1", "Card", "6000.00", "24.9900%", "150.00", "19", "1268.70"])
        self.assertEqual(len(rows), 4)


class InvestmentsCsvTest(unittest.TestCase):
    """Exit criterion: the positions CSV re-parses to the same positions."""

    def test_positions_reparse(self):
        import json
        vector = json.load(open(os.path.join(REPO_ROOT, "tests", "app", "vectors", "portfolio_20.json")))
        result = app.calculate("investments", vector["rows"], vector["as_of"])
        buffer = io.StringIO()
        app.export_csv(result, buffer)
        rows = list(csv.reader(io.StringIO(buffer.getvalue())))
        self.assertEqual(rows[0], ["symbol", "shares", "avg_cost", "cost_basis", "price", "value", "gain", "gain_pct", "annualized"])
        self.assertEqual(len(rows), 21)
        parsed = []
        for row in rows[1:]:
            parsed.append([row[0], int(row[1].replace(".", ""))] + [int(v.replace(".", "")) for v in row[2:7]]
                          + [int(row[7].rstrip("%").replace(".", "")), int(row[8].rstrip("%").replace(".", ""))])
        self.assertEqual(parsed, vector["expected"]["positions"])


if __name__ == "__main__":
    unittest.main()
