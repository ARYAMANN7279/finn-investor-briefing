"""Filing PDFs -> structured facts, with a cross-check against an independent source.

Results numbers: the model reads the results table out of the filing PDF; we convert units in code (never the model),
then compare each figure with Screener's quarterly table. "verified" means the two independent sources agree.
"""
from __future__ import annotations

import json
import pathlib
import re

from . import llm, pdftext

ENRICH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "enrich.json"
TO_CRORE = {"rs_crore": 1.0, "rs_lakh": 0.01, "rs_million": 0.1, "rs_billion": 100.0}

NUM = {"type": "NUMBER", "nullable": True}
COL = {"type": "OBJECT", "properties": {"revenue": NUM, "total_income": NUM, "profit_before_tax": NUM, "net_profit": NUM, "interest_earned": NUM,
                                         "interest_expended": NUM},
       "required": ["revenue", "profit_before_tax", "net_profit"]}
RESULTS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "basis": {"type": "STRING", "enum": ["consolidated", "standalone"]},
        "unit": {"type": "STRING", "enum": list(TO_CRORE)},
        "current_quarter_end": {"type": "STRING"},
        "current": COL, "previous_quarter": COL, "year_ago_quarter": COL,
        "note": {"type": "STRING"},
    },
    "required": ["basis", "unit", "current_quarter_end", "current", "previous_quarter", "year_ago_quarter"],
}
RESULTS_SYSTEM = (
    "You read Indian listed-company quarterly results tables from exchange filings. Copy numbers exactly as printed, "
    "in the unit the table uses; never convert units and never calculate. Use null for anything not printed. "
    "If a consolidated table exists use it, otherwise the standalone one."
)
RESULTS_PROMPT = """From the pages below, extract the results for the single quarter named in the filing title: "{title}".
Columns wanted: the quarter itself, the immediately preceding quarter, and the same quarter a year earlier (all three are printed side by side).
- revenue: "Revenue from operations" (for banks and NBFCs use total income from operations if that is the top line).
- net_profit: profit for the period after tax (the total, before the split between owners and minority interest).
- For banks/NBFCs also fill interest_earned and interest_expended if printed.
Pick `unit` from how the table states its figures (Rs. in crore / lakh / million / billion).
Do not use half-year or nine-month or full-year columns.

PAGES:
{pages}"""


def pick_pages(pages: list[str], limit: int = 5) -> str:
    """Pages that look like the results table, best first, as one prompt-sized block."""
    scored = []
    for i, t in enumerate(pages):
        low = t.lower()
        s = 3 * ("profit before tax" in low or "profit/(loss) before tax" in low) + 2 * ("revenue from operations" in low or "interest earned" in low)
        s += ("net profit" in low or "profit for the" in low) + ("quarter ended" in low) + ("consolidated" in low) + ("crore" in low or "lakh" in low or "million" in low)
        if s >= 6:
            scored.append((s, i))
    scored.sort(key=lambda x: (-x[0], x[1]))
    keep = sorted(i for _, i in scored[:limit])
    return "\n\n".join(f"--- page {i + 1} ---\n{pages[i][:9000]}" for i in keep)


def extract_results(url: str, title: str) -> dict:
    block = pick_pages(pdftext.pages(url))
    if not block:
        return {"status": "no_table", "why": "No page in the filing looks like a results table (it may be a scanned image)."}
    r = llm.ask(RESULTS_PROMPT.format(title=title, pages=block), tier="bulk", system=RESULTS_SYSTEM, schema=RESULTS_SCHEMA)
    return {"status": "extracted", "model": r["model"], "data": r["data"]}


def crore(x, unit):
    return None if x is None else x * TO_CRORE[unit]


def cross_check(data: dict, labels: list[str], rows: dict, label: str, financial: bool) -> dict:
    """Compare the filing's current-quarter figures with Screener's table. Tolerance 1.5% (rounding, restated lines)."""
    if label not in labels:
        return {"state": "unchecked", "why": f"Screener has no {label} column yet."}
    i = labels.index(label)
    unit = data["unit"]
    cur = data["current"]
    top = rows.get("Sales") or rows.get("Revenue")
    pairs = [("revenue", crore(cur.get("revenue"), unit), top[i] if top else None),
             ("profit_before_tax", crore(cur.get("profit_before_tax"), unit), (rows.get("Profit before tax") or [None] * 99)[i]),
             ("net_profit", crore(cur.get("net_profit"), unit), (rows.get("Net Profit") or [None] * 99)[i])]
    detail, bad = [], 0
    for name, a, b in pairs:
        if a is None or b in (None, 0):
            detail.append({"metric": name, "filing": a, "screener": b, "ok": None})
            continue
        ok = abs(a - b) / abs(b) <= 0.015
        bad += not ok
        detail.append({"metric": name, "filing": round(a, 2), "screener": b, "ok": ok})
    checked = [d for d in detail if d["ok"] is not None]
    state = "unchecked" if not checked else ("verified" if not bad else "mismatch")
    return {"state": state, "detail": detail}


def load() -> dict:
    return json.loads(ENRICH.read_text()) if ENRICH.exists() else {}


def save(db: dict) -> None:
    ENRICH.write_text(json.dumps(db, indent=1, ensure_ascii=False))


def quarter_label(title: str) -> str | None:
    m = re.search(r"ended\s+(?:on\s+)?(?:\d{1,2}\s*(?:st|nd|rd|th)?\s+)?([A-Za-z]+)\s*(?:\d{1,2}\s*(?:st|nd|rd|th)?)?,?\s*(\d{4})", title, re.I)
    return f"{m.group(1)[:3].title()} {m.group(2)}" if m else None
