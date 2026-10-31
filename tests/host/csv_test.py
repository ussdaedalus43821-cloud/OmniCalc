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
        cls.result = app.calculate("200,000.00", "6.5", "360", "0")
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


if __name__ == "__main__":
    unittest.main()
