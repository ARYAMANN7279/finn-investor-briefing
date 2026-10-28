import unittest
from unittest.mock import patch

from finn import enrich, extract, research


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

    def test_partial_match_is_not_called_verified(self):
        rows = {"Sales": [100.0, 200.0]}
        c = extract.cross_check(self.data(), self.labels, rows, "Sep 2026", False)
        self.assertEqual(c["state"], "unchecked")
        self.assertEqual(c["checked"], 1)

    def test_zero_is_a_valid_comparable_value(self):
        data = self.data(profit_before_tax=0.0, net_profit=0.0)
        rows = {"Sales": [100.0, 200.0], "Profit before tax": [10.0, 0.0], "Net Profit": [8.0, 0.0]}
        c = extract.cross_check(data, self.labels, rows, "Sep 2026", False)
        self.assertEqual(c["state"], "verified")

    def test_missing_quarter_is_unchecked(self):
        self.assertEqual(extract.cross_check(self.data(), self.labels, self.rows, "Dec 2026", False)["state"], "unchecked")

    def test_quarter_label(self):
        self.assertEqual(extract.quarter_label("Results For The Quarter And Half Year Ended September 30, 2026"), "Sep 2026")
        self.assertEqual(extract.quarter_label("Quarter ended 30th September, 2026"), "Sep 2026")

    def test_enrich_refreshes_saved_checks_without_reextracting(self):
        snapshot = {"companies": [{"financial": False, "quarters": {
            "labels": ["Sep 2026"], "rows": {"Sales": [200.0], "Profit before tax": [20.0], "Net Profit": [15.0]}},
            "filings": [{"url": "filing", "category": "results", "subtype": "outcome", "title": "Results quarter ended September 30, 2026"}]}]}
        db = {"filing": {"kind": "results", "status": "extracted", "data": {
            "unit": "rs_crore", "current": {"revenue": 200.0, "profit_before_tax": 20.0, "net_profit": 15.0}},
            "check": {"state": "verified", "detail": []}}}
        with patch("finn.enrich.extract.save") as save:
            self.assertEqual(enrich.refresh_checks(snapshot, db), 1)
            save.assert_called_once_with(db)
        self.assertEqual(db["filing"]["check"]["checked"], 3)


class Research(unittest.TestCase):
    def test_quarters_after_call(self):
        self.assertEqual(research.quarters_after("Concall Jun 2026", ["Mar 2026", "Jun 2026", "Sep 2026"]), ["Jun 2026", "Sep 2026"])

    def test_numbers_must_come_from_the_table(self):
        tbl = "Jun 2026 | 10542.0 | 17.9"
        self.assertTrue(research.numbers_ok("revenue was Rs 10,542 crore, up 17.9%", tbl))
        self.assertFalse(research.numbers_ok("revenue was Rs 12,345 crore", tbl))

    def test_number_must_match_as_a_value_not_a_substring(self):
        self.assertFalse(research.numbers_ok("Revenue was 1,234 crore", "quarter | 91,234 crore"))

    def test_calendar_year_in_horizon_is_not_a_financial_figure(self):
        self.assertTrue(research.numbers_ok("The target runs through Calendar Year 2026 or early 2027.", "Sep 2026 | revenue 123.0"))

    def test_judge_table_includes_code_computed_trailing_margins(self):
        co = research.screener.Company(symbol="ACME")
        co.quarters = {"labels": ["Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026"], "rows": {
            "Sales": [100.0, 110.0, 120.0, 130.0], "Operating Profit": [20.0, 22.0, 24.0, 26.0], "Net Profit": [10.0, 11.0, 12.0, 13.0]}}
        row = research.table(co).splitlines()[-1].split(" | ")
        self.assertEqual(row[3], "460.0")
        self.assertEqual(row[5], "92.0")
        self.assertEqual(row[7], "20.0")
        self.assertEqual(row[10], "46.0")

    def test_quote_matching_ignores_punctuation_and_case(self):
        a = research._norm("We’ll maintain the 18-20% band, “going ahead”.")
        self.assertIn(research._norm("maintain the 18-20% band going ahead"), a)

    def test_extracted_quote_must_be_on_its_cited_page(self):
        quote = "We expect capacity to grow over the next three years."
        response = {"data": {"claims": [
            {"statement": "Capacity will grow.", "quote": quote, "page": 1, "speaker": "management", "topic": "expansion", "target": "grow", "horizon": "three years"},
            {"statement": "Capacity will grow.", "quote": quote, "page": 2, "speaker": "management", "topic": "expansion", "target": "grow", "horizon": "three years"},
        ], "facts": []}, "model": "test-model"}
        doc = {"label": "Annual Report", "url": "https://example.test/report.pdf", "kind": "annual_report",
               "text": "[p 1] We expect capacity to grow over the next three years.\n[p 2] Different page text.",
               "norm": "", "page_text": {1: "We expect capacity to grow over the next three years.", 2: "Different page text."}}
        with patch("finn.research.pdftext.chunks", return_value=["page-tagged text"]), \
             patch("finn.research.llm.ask", return_value=response):
            items = research.extract_doc(doc, "0")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["page"], 1)


if __name__ == "__main__":
    unittest.main()
