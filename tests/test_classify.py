import unittest

from finn.classify import classify

# Real titles seen on Screener's announcement lists on 2026-10-27 -> (category, subtype)
CASES = [
    ("Announcement under Regulation 30 (LODR)-Change in Management", "management_change", "senior"),
    ("Announcement under Regulation 30 (LODR)-Resignation of Director", "management_change", "director"),
    ("Announcement under Regulation 30 (LODR)-Change in Directorate", "management_change", "director"),
    ("Financial Results For The Quarter And Half Year Ended September 30, 2026 And Declaration Of Interim Dividend", "results", "outcome"),
    ("Board Meeting Outcome for Financial Results For The Quarter And Half Year Ended September 30, 2026", "results", "outcome"),
    ("Board Meeting Intimation for Unaudited Standalone And Consolidated Financial Results Of The Company For The Qu", "results", "intimation"),
    ("Report Of Auditors On Financial Statements For The Quarter And Half Year Ended September 30, 2026 With UDIN", "results", "auditor_report"),
    ("Announcement under Regulation 30 (LODR)-Updates on Acquisition", "M&A", "deal"),
    ("Intimation Under Regulation 30 Of The SEBI (LODR) Regulations, 2015 - Incorporation Of Wholly Owned Subsidiary", "M&A", "deal"),
    ("Announcement under Regulation 30 (LODR)-Diversification / Disinvestment", "M&A", "deal"),
    ("Initial Public Offer Of Jio Platforms Limited - Update", "fund_raise", "ipo"),
    ("Newspaper Clipping - Proposed Initial Public Offer Of Jio Platforms Limited -Reservation For Eligible RIL Shar", "unclassified", "newspaper_ad"),
    ("Intimation of Repayment of Commercial Paper (CP)", "fund_raise", "financing"),
    ("Announcement under Regulation 30 (LODR) - Bagging/receiving of order(s) or contract(s) 27 Oct", "press_release", "order"),
    ("Announcement under Regulation 30 (LODR)-Credit Rating", "credit_rating", "rating"),
    ("Announcement under Regulation 30 (LODR)-Earnings Call Transcript", "earnings_call", "transcript"),
    ("Announcement under Regulation 30 (LODR)-Analyst / Investor Meet - Intimation", "investor_meetings", "intimation"),
    ("Announcement Under Regulation 30 (LODR) - Analyst(S) / Investor(S) Meet - Intimation", "investor_meetings", "intimation"),
    ("Announcement under Regulation 30 (LODR)-Allotment of ESOP / ESPS", "unclassified", "esop"),
    ("Announcement under Regulation 30 (LODR)-Allotment", "unclassified", "allotment"),
    ("Corporate Action-Board approves Dividend", "dividend", "declared"),
    ("Disclosures under Reg. 29(2) of SEBI (SAST) Regulations, 2011 7 Oct", "insider_trading", "disclosure"),
    ("Compliances-Certificate under Reg. 74 (5) of SEBI (DP) Regulations, 2018", "unclassified", "compliance"),
    ("Closure of Trading Window", "unclassified", "trading_window"),
    ("Corporate Insolvency Resolution Process (CIRP)-Updates", "litigation", "regulatory"),
    ("USFDA Inspection At Invagen Manufacturing Facility In Hauppauge, Long Island, New York, USA", "litigation", "regulatory"),
    ("Shareholder Meeting / Postal Ballot-Notice of Postal Ballot", "postal_ballot", "ballot"),
    ("Media Statement", "press_release", "release"),
    ("General Updates", "unclassified", "update"),
]


class Classify(unittest.TestCase):
    def test_real_titles(self):
        for title, cat, sub in CASES:
            with self.subTest(title=title[:60]):
                got = classify(title)
                self.assertEqual((got.category, got.subtype), (cat, sub))

    def test_unknown_is_flagged_ambiguous(self):
        got = classify("Some entirely new kind of filing")
        self.assertTrue(got.ambiguous)

    def test_a_results_outcome_outranks_its_intimation(self):
        self.assertGreater(classify("Financial Results For The Quarter Ended 30th September").score,
                           classify("Board Meeting Intimation for Unaudited Financial Results").score)

    def test_routine_is_low_and_deals_are_high(self):
        self.assertLess(classify("Announcement under Regulation 30 (LODR)-Newspaper Publication").score, 10)
        self.assertGreater(classify("Announcement under Regulation 30 (LODR)-Acquisition").score, 70)


if __name__ == "__main__":
    unittest.main()
