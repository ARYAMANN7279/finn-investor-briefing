import unittest

from finn import extract, research


class CrossCheck(unittest.TestCase):
    labels = ["Jun 2026", "Sep 2026"]
    rows = {"Sales": [100.0, 200.0], "Profit before tax": [10.0, 20.0], "Net Profit": [8.0, 15.0]}

    def data(self, **cur):
        base = {"revenue": 2000.0, "profit_before_tax": 200.0, "net_profit": 150.0}
        return {"unit": "rs_million", "current": {**base, **cur}}  # million -> crore is x0.1

    def test_units_converted_in_code(self):
        c = extract.cross_check(self.data(), self.labels, self.rows, "Sep 2026", False)
        self.assertEqual(c["state"], "verified")

    def test_mismatch_is_flagged(self):
        c = extract.cross_check(self.data(net_profit=300.0), self.labels, self.rows, "Sep 2026", False)
        self.assertEqual(c["state"], "mismatch")
        self.assertFalse([d for d in c["detail"] if d["metric"] == "net_profit"][0]["ok"])

    def test_missing_quarter_is_unchecked(self):
        self.assertEqual(extract.cross_check(self.data(), self.labels, self.rows, "Dec 2026", False)["state"], "unchecked")

    def test_quarter_label(self):
        self.assertEqual(extract.quarter_label("Results For The Quarter And Half Year Ended September 30, 2026"), "Sep 2026")
        self.assertEqual(extract.quarter_label("Quarter ended 30th September, 2026"), "Sep 2026")


class Research(unittest.TestCase):
    def test_quarters_after_call(self):
        self.assertEqual(research.quarters_after("Concall Jun 2026", ["Mar 2026", "Jun 2026", "Sep 2026"]), ["Jun 2026", "Sep 2026"])

    def test_numbers_must_come_from_the_table(self):
        tbl = "Jun 2026 | 10542.0 | 17.9"
        self.assertTrue(research.numbers_ok("revenue was Rs 10,542 crore, up 17.9%", tbl))
        self.assertFalse(research.numbers_ok("revenue was Rs 12,345 crore", tbl))

    def test_quote_matching_ignores_punctuation_and_case(self):
        a = research._norm("We’ll maintain the 18-20% band, “going ahead”.")
        self.assertIn(research._norm("maintain the 18-20% band going ahead"), a)


if __name__ == "__main__":
    unittest.main()
