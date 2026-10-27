"""Research sheet for any NSE ticker, from primary sources only (annual reports and concall transcripts).

    python3 -m finn.research TICKER [TICKER ...]

Pipeline, cheapest step first:
  1. PDF -> text (PyMuPDF) -> page-tagged chunks. Annual reports are cut down to the pages that talk about outlook, risks and
     strategy before any model sees them.
  2. Bulk model (Flash-lite) reads each chunk and returns forward-looking claims and plain facts, each with a verbatim quote.
  3. Code checks every quote against the source text. A claim whose quote is not in the document is dropped.
  4. Strong tier (Pro if the key has quota, else the best Flash) judges the older promises against the quarterly numbers
     that followed, and writes the business / narrative / bull / bear view, citing claim ids only.
  5. Code turns the ids back into quotes with document and page. Nothing in the sheet is a claim without a source.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time

from . import llm, pdftext
from .sources import screener

OUT = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "research"

ITEM = {"type": "OBJECT", "properties": {
    "statement": {"type": "STRING"}, "quote": {"type": "STRING"}, "page": {"type": "INTEGER"}},
    "required": ["statement", "quote", "page"]}
CLAIM = {"type": "OBJECT", "properties": {
    **ITEM["properties"],
    "topic": {"type": "STRING", "enum": ["revenue_growth", "margin", "profit", "capex", "debt_cash", "expansion", "product", "demand", "cost", "other"]},
    "target": {"type": "STRING", "nullable": True}, "horizon": {"type": "STRING", "nullable": True}},
    "required": ["statement", "quote", "page", "topic"]}
FACT = {"type": "OBJECT", "properties": {
    **ITEM["properties"], "kind": {"type": "STRING", "enum": ["business", "segment", "risk", "balance_sheet", "cash_flow", "other"]}},
    "required": ["statement", "quote", "page", "kind"]}
CHUNK_SCHEMA = {"type": "OBJECT", "properties": {"claims": {"type": "ARRAY", "items": CLAIM}, "facts": {"type": "ARRAY", "items": FACT}},
                "required": ["claims", "facts"]}
CHUNK_SYSTEM = ("You extract evidence from a company's annual report or earnings-call transcript for an equity analyst. "
                "Use only the text given. `quote` must be copied word for word from the text (at most 40 words, no ellipses, no edits). "
                "`page` is the number from the nearest '[p N]' marker before the quote.")
CHUNK_PROMPT = """Document: {label}.
Return:
- claims: forward-looking commitments, guidance or targets that management states (growth rates, margins, capex, launches, store/capacity additions, debt goals). Put any number or date they give in `target` / `horizon`. Skip history and generic optimism. At most 10, the most specific first.
- facts: plain statements about what the business does, its segments, its main risks, its borrowings or cash position and cash flow. At most 8, the most useful first.
If the chunk has none, return empty lists.

TEXT:
{text}"""

JUDGE_SCHEMA = {"type": "OBJECT", "properties": {"verdicts": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "id": {"type": "STRING"},
    "verdict": {"type": "STRING", "enum": ["delivered", "partly", "missed", "too_early", "not_measurable"]},
    "evidence": {"type": "STRING"}, "quarters": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["id", "verdict", "evidence"]}}}, "required": ["verdicts"]}
JUDGE_SYSTEM = ("You compare what management promised on an earnings call with what the company then reported. "
                "Use only the promises and the quarterly table given. Cite the quarters (labels as in the table) and the figures you used in `evidence`, "
                "in one or two plain sentences. If the table cannot test the promise (new products, qualitative goals), say not_measurable. "
                "If too little time has passed, say too_early. Never use outside knowledge.")
JUDGE_PROMPT = """Company: {name}. Quarterly results table (figures in Rs crore, oldest to newest; OPM = operating profit / revenue):
{table}

Promises made on earlier calls (id, call date, promise, quote):
{promises}

For each id give a verdict."""

VIEW_SCHEMA = {"type": "OBJECT", "properties": {
    "business": {"type": "STRING"},
    "business_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
    "narrative": {"type": "STRING"}, "narrative_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
    "bull": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"point": {"type": "STRING"}, "ids": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["point", "ids"]}},
    "bear": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"point": {"type": "STRING"}, "ids": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["point", "ids"]}},
    "balance": {"type": "STRING"}, "balance_ids": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["business", "business_ids", "narrative", "narrative_ids", "bull", "bear", "balance", "balance_ids"]}
VIEW_SYSTEM = ("You write a research view of one company for a retail investor from a list of sourced statements. "
               "Every sentence must rest on statements from the list; cite them by id. Do not add anything from outside the list. "
               "Write plainly. If the list cannot support a section, say so in that section instead of guessing.")
VIEW_PROMPT = """Company: {name}.
Annual-report facts and management claims, each as: id | source | statement
{items}

Write:
- business: three sentences on what the company does and how it earns money.
- narrative: how the story in the annual report compares with what management says on recent calls: where they agree, where the emphasis moved.
- bull / bear: three to four points each, the strongest the evidence allows. A bear point may be an unmet promise or a risk the company itself names.
- balance: two sentences on borrowings, cash and cash flow, only if the statements give them.
Cite ids in every part."""


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"[^a-z0-9%.]+", " ", s.lower()).strip()


def _tagged(pages: list[str], idx: list[int]) -> str:
    return "\n".join(f"[p {i + 1}]\n{pages[i]}" for i in idx)


def ar_pages(pages: list[str], limit: int = 26) -> list[int]:
    """The pages of an annual report most likely to hold outlook, risk and balance-sheet language."""
    words = ("outlook", "risk", "strategy", "guidance", "borrowings", "cash flow", "management discussion", "we expect", "going forward", "targets", "capex", "capital expenditure")
    scored = sorted(((sum(w in p.lower() for w in words), i) for i, p in enumerate(pages) if len(p) > 600), reverse=True)
    return sorted(i for s, i in scored[:limit] if s >= 2)


def read_doc(label: str, url: str, kind: str) -> dict | None:
    try:
        pages = pdftext.pages(url)
    except Exception as err:
        print("  skip", label, err)
        return None
    idx = ar_pages(pages) if kind == "annual_report" else list(range(len(pages)))
    if not idx:
        return None
    text = _tagged(pages, idx)
    return {"label": label, "url": url, "kind": kind, "text": text, "norm": _norm(text), "pages": len(pages)}


def extract_doc(doc: dict, tag: str) -> list[dict]:
    items = []
    for n, chunk in enumerate(pdftext.chunks(doc["text"], 22000)):
        r = llm.ask(CHUNK_PROMPT.format(label=doc["label"], text=chunk), tier="bulk", system=CHUNK_SYSTEM, schema=CHUNK_SCHEMA)
        for kind, key in (("claim", "claims"), ("fact", "facts")):
            for it in r["data"].get(key, []):
                q = _norm(it["quote"])
                if len(q) < 25 or q not in doc["norm"]:  # not a verbatim quote of this document: drop it
                    continue
                items.append({"id": f"{tag}.{len(items)}", "type": kind, "doc": doc["label"], "url": doc["url"], **it, "model": r["model"]})
    seen, out = set(), []
    for it in items:  # the same quote can come back from overlapping chunks
        k = _norm(it["quote"])[:80]
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def table(co: screener.Company, n: int = 12) -> str:
    q = co.quarters
    top = co.top_line()
    op = q["rows"].get("Operating Profit")
    pat = q["rows"].get("Net Profit")
    lines = ["quarter | revenue | operating profit | OPM% | net profit"]
    for i in range(max(0, len(q["labels"]) - n), len(q["labels"])):
        r = top[i] if top else None
        o = op[i] if op else None
        opm = f"{o / r * 100:.1f}" if r and o is not None else "n/a"
        lines.append(f"{q['labels'][i]} | {r} | {o} | {opm} | {pat[i] if pat else 'n/a'}")
    return "\n".join(lines)


def trajectory(co: screener.Company) -> dict:
    """Pure arithmetic on Screener's quarterly table: no model involved."""
    q, top = co.quarters, co.top_line()
    if not top:
        return {}
    rows = []
    for i in range(len(q["labels"])):
        yago = top[i - 4] if i >= 4 else None
        op = (q["rows"].get("Operating Profit") or [None] * len(top))[i]
        rows.append({"q": q["labels"][i], "revenue": top[i], "opm": round(op / top[i] * 100, 1) if op is not None and top[i] else None,
                     "pat": (q["rows"].get("Net Profit") or [None] * len(top))[i],
                     "rev_yoy": round((top[i] - yago) / yago * 100, 1) if yago and top[i] is not None else None})
    return {"rows": rows[-12:], "financial": co.is_financial}


def build(symbol: str, calls: int = 4, reports: int = 1) -> dict:
    co = screener.fetch(symbol)
    print(symbol, co.name)
    docs = []
    for r in co.annual_reports[:reports]:
        d = read_doc(r["label"], r["url"], "annual_report")
        if d:
            docs.append(d)
    done = 0
    for c in co.concalls:
        if done >= calls:
            break
        if c.get("transcript"):
            d = read_doc(f"Concall {c['label']}", c["transcript"], "concall")
            if d:
                docs.append(d)
                done += 1
    items = []
    for n, d in enumerate(docs):
        got = extract_doc(d, str(n))
        print(f"  {d['label']}: {len(got)} verified items from {d['pages']} pages")
        items += got
    by_id = {it["id"]: it for it in items}
    # promised vs delivered: quantified claims from the calls except the newest one
    call_docs = [d for d in docs if d["kind"] == "concall"]
    older = {d["label"] for d in call_docs[1:]}
    promises = [it for it in items if it["type"] == "claim" and it["doc"] in older and it.get("target")][:24]
    verdicts = []
    if promises:
        listing = "\n".join(f"{p['id']} | {p['doc']} | {p['statement']} (target: {p['target']}, horizon: {p.get('horizon')}) | \"{p['quote']}\"" for p in promises)
        j = llm.ask(JUDGE_PROMPT.format(name=co.name, table=table(co), promises=listing), tier="strong", system=JUDGE_SYSTEM, schema=JUDGE_SCHEMA)
        for v in j["data"]["verdicts"]:
            p = by_id.get(v["id"])
            if p:
                verdicts.append({**v, "claim": p["statement"], "target": p.get("target"), "horizon": p.get("horizon"), "quote": p["quote"], "doc": p["doc"],
                                 "page": p["page"], "url": p["url"], "judge": j["model"]})
    # business / narrative / bull / bear view, citing ids only
    pool = sorted(items, key=lambda it: (it["type"] != "fact", it["id"]))[:70]
    listing = "\n".join(f"{it['id']} | {it['doc']} | {it['statement']}" for it in pool)
    view = llm.ask(VIEW_PROMPT.format(name=co.name, items=listing), tier="strong", system=VIEW_SYSTEM, schema=VIEW_SCHEMA)
    v, view_model = view["data"], view["model"]

    def cite(ids):
        return [{k: by_id[i][k] for k in ("doc", "url", "page", "quote")} for i in ids if i in by_id]

    sheet = {
        "symbol": symbol, "name": co.name, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sources": [{"label": d["label"], "url": d["url"], "kind": d["kind"]} for d in docs],
        "business": {"text": v["business"], "cites": cite(v["business_ids"])},
        "narrative": {"text": v["narrative"], "cites": cite(v["narrative_ids"])},
        "balance": {"text": v["balance"], "cites": cite(v["balance_ids"])},
        "bull": [{"point": x["point"], "cites": cite(x["ids"])} for x in v["bull"]],
        "bear": [{"point": x["point"], "cites": cite(x["ids"])} for x in v["bear"]],
        "promised": verdicts,
        "trajectory": trajectory(co),
        "stats": {"documents": len(docs), "verified_items": len(items), "view_model": view_model},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{symbol}.json").write_text(json.dumps(sheet, indent=1, ensure_ascii=False))
    index = json.loads((OUT / "index.json").read_text()) if (OUT / "index.json").exists() else {}
    index[symbol] = {"name": co.name, "built_at": sheet["built_at"], "promises": len(verdicts), "sources": len(docs)}
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    return sheet


def main() -> None:
    for sym in sys.argv[1:] or ["ASIANPAINT"]:
        s = build(sym.upper())
        print(sym, "->", s["stats"], len(s["promised"]), "promises judged")
    print(json.dumps(llm.ledger()))


if __name__ == "__main__":
    main()
