import unittest

from finn.sources import prices, screener

PAGE = """
<h1 class="h2 margin-0">Acme Ltd</h1>
<ul id="top-ratios"><li><span class="name"> Market Cap </span> <span class="nowrap value"> ₹ <span class="number">1,000</span> Cr. </span></li></ul>
<section id="quarters"><div data-result-table><table><thead><tr><th class="text"></th>
<th data-date-key="2026-03-31"> Mar 2026 </th><th data-date-key="2026-06-30"> Jun 2026 </th></tr></thead><tbody>
<tr><td class="text"><button>Sales&nbsp;<span>+</span></button></td><td>1,000</td><td>1,100</td></tr>
<tr><td class="text">OPM %</td><td>18%</td><td>20%</td></tr>
<tr><td class="text">Raw PDF</td><td><a href="https://x/q1.pdf">PDF</a></td><td></td></tr></tbody></table></div></section>
<section id="documents"><h3>Announcements</h3><ul class="list-links">
<li><a href="https://bse.example/a.pdf?x=1&amp;y=2"> Outcome of Board Meeting <div class="ink-600"><time datetime="2026-10-24T21:47:58+05:30">24 Oct</time> - x</div></a></li></ul>
<h3>Annual reports</h3><ul><li><a href="https://x/ar26.pdf">Annual Report 2026</a></li></ul>
<h3 class="margin-0">Concalls</h3><ul class="list-links"><li class="flex flex-gap-8 flex-wrap-420"><div style="width: 74px">Jul 2026</div>
<a class="button-chip" href="https://x/t.pdf">Transcript</a><a class="button-chip" href="https://x/p.pdf">PPT</a></li></ul></section>
"""


class ScreenerParse(unittest.TestCase):
    def test_parse(self):
        co = screener.parse_company(PAGE, "ACME")
        self.assertEqual(co.name, "Acme Ltd")
        self.assertEqual(co.ratios["Market Cap"], "₹ 1,000 Cr.")
        self.assertEqual(co.quarters["labels"], ["Mar 2026", "Jun 2026"])
        self.assertEqual(co.quarters["rows"]["Sales"], [1000.0, 1100.0])
        self.assertEqual(co.quarters["rows"]["OPM %"], [18.0, 20.0])
        self.assertEqual(co.quarters["pdfs"], ["https://x/q1.pdf", None])
        self.assertEqual(co.top_line(), [1000.0, 1100.0])
        self.assertFalse(co.is_financial)
        self.assertEqual(co.filings[0]["url"], "https://bse.example/a.pdf?x=1&y=2")
        self.assertEqual(co.filings[0]["title"], "Outcome of Board Meeting")
        self.assertEqual(co.annual_reports[0]["label"], "Annual Report 2026")
        self.assertEqual(co.concalls[0], {"label": "Jul 2026", "transcript": "https://x/t.pdf", "ppt": "https://x/p.pdf"})


class Prices(unittest.TestCase):
    def bars(self, vols, closes):
        return [prices.Bar(f"d{i}", c, v) for i, (c, v) in enumerate(zip(closes, vols))]

    def test_unusual_volume_and_move(self):
        b = self.bars([100] * 21 + [450], [100.0] * 21 + [106.0])
        r = prices.unusual(b, vol_mult=2.0, move_pct=4.0)
        self.assertEqual(r["vol_multiple"], 4.5)
        self.assertTrue(r["volume_alert"] and r["move_alert"])
        self.assertEqual(r["move_pct"], 6.0)

    def test_quiet_day(self):
        b = self.bars([100] * 22, [100.0] * 22)
        r = prices.unusual(b)
        self.assertFalse(r["volume_alert"] or r["move_alert"])

    def test_open_session_bar_is_dropped(self):
        import datetime as dt
        b = self.bars([100] * 3, [1.0] * 3)
        b[-1].date = "2026-10-27"
        midday = dt.datetime(2026, 10, 27, 11, 54, tzinfo=prices.IST)
        evening = dt.datetime(2026, 10, 27, 18, 0, tzinfo=prices.IST)
        self.assertEqual(len(prices.completed(b, midday)), 2)
        self.assertEqual(len(prices.completed(b, evening)), 3)

    def test_parse_chart_skips_nulls(self):
        payload = {"chart": {"result": [{"timestamp": [1793000000, 1793086400], "indicators": {"quote": [{"close": [10.0, None], "volume": [5, None]}]}}]}}
        self.assertEqual(len(prices.parse_chart(payload)), 1)


if __name__ == "__main__":
    unittest.main()
