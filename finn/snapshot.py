"""Builds app/data/snapshot.json: everything the mobile app needs to rank, window and alert in the browser.

    python3 -m finn.snapshot            # portfolio + research names, from cache where fresh
Filings are classified here (free rules); results numbers and research sheets are added by their own steps and merged in.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

from . import universe
from .classify import classify
from .sources import prices, screener

OUT = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "snapshot.json"


def company_entry(sym: str, sector: str, in_portfolio: bool) -> dict:
    co = screener.fetch(sym)
    bars = prices.completed(prices.fetch(sym))
    filings = []
    for f in co.filings:
        lab = classify(f["title"])
        filings.append({**f, "category": lab.category, "subtype": lab.subtype, "score": lab.score, "ambiguous": lab.ambiguous})
    q = co.quarters
    return {
        "symbol": sym, "name": co.name, "sector": sector, "portfolio": in_portfolio, "financial": co.is_financial,
        "ratios": {k: v for k, v in co.ratios.items() if k in ("Market Cap", "Current Price", "Stock P/E", "ROCE", "ROE", "Dividend Yield")},
        "last": {"date": bars[-1].date, "close": round(bars[-1].close, 2)},
        "stats": prices.daily_stats(bars),
        "spark": [round(b.close, 2) for b in bars[-40:]],
        "filings": filings,
        "quarters": {"labels": q["labels"][-6:], "rows": {k: v[-6:] for k, v in q["rows"].items() if k in
                     ("Sales", "Revenue", "Interest", "Operating Profit", "Financing Profit", "Other Income", "Depreciation", "Profit before tax", "Net Profit")},
                     "pdfs": q.get("pdfs", [])[-6:]},
        "docs": {"annual_reports": co.annual_reports[:3], "concalls": co.concalls[:6]},
    }


def build(symbols: dict[str, tuple[str, bool]]) -> dict:
    companies, failed = [], {}
    for sym, (sector, port) in symbols.items():
        try:
            companies.append(company_entry(sym, sector, port))
        except Exception as exc:  # noqa: BLE001 - one bad ticker must not take the whole briefing down
            failed[sym] = f"{type(exc).__name__}: {exc}"
    return {"built_at": dt.datetime.now(prices.IST).isoformat(timespec="seconds"), "companies": companies, "failed": failed}


def main() -> int:
    syms = {s: (sec, True) for s, sec in universe.PORTFOLIO.items()} | {s: (sec, False) for s, sec in universe.RESEARCH.items()}
    snap = build(syms)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    n = sum(len(c["filings"]) for c in snap["companies"])
    print(f"{len(snap['companies'])} companies, {n} filings, failed={snap['failed']} -> {OUT}")
    return 1 if snap["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
