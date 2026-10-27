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
    "speaker": {"type": "STRING", "enum": ["management", "analyst", "unclear"]},
    "topic": {"type": "STRING", "enum": ["revenue_growth", "margin", "profit", "capex", "debt_cash", "expansion", "product", "demand", "cost", "other"]},
    "target": {"type": "STRING", "nullable": True}, "horizon": {"type": "STRING", "nullable": True}},
    "required": ["statement", "quote", "page", "topic", "speaker"]}
FACT = {"type": "OBJECT", "properties": {
    **ITEM["properties"], "kind": {"type": "STRING", "enum": ["business", "segment", "risk", "balance_sheet", "cash_flow", "other"]}},
    "required": ["statement", "quote", "page", "kind"]}
CHUNK_SCHEMA = {"type": "OBJECT", "properties": {"claims": {"type": "ARRAY", "items": CLAIM}, "facts": {"type": "ARRAY", "items": FACT}},
                "required": ["claims", "facts"]}
CHUNK_SYSTEM = ("You extract evidence from a company's annual report or earnings-call transcript for an equity analyst. "
                "Use only the text given. `quote` must be copied word for word from the text (at most 40 words, no ellipses, no edits). "
                "`page` is the number from the nearest '[p N]' marker before the quote. In a transcript, set `speaker` to who said the quote: "
                "company management (CEO, CFO, executives) or an analyst asking a question. Only management's own words count as claims; "
                "an analyst's question that mentions a number is not a company claim.")
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
    "evidence": {"type": "STRING"}, "quarters": {"type": "ARRAY", "items": {"type": "STRING"}},
    "same_as": {"type": "STRING", "nullable": True}},
    "required": ["id", "verdict", "evidence"]}}}, "required": ["verdicts"]}
JUDGE_SYSTEM = ("You compare what management promised on an earnings call with what the company then reported. "
                "Use only the promises and the quarterly table given. Cite the quarters (labels as in the table) and the figures you used in `evidence`, "
                "in one or two plain sentences. If the table cannot test the promise (new products, qualitative goals), say not_measurable. "
                "If too little time has passed, say too_early. Never use outside knowledge.")
JUDGE_PROMPT = """Company: {name}. Quarterly results table (figures in Rs crore, oldest to newest; OPM = operating profit / revenue; YoY and last-4-quarter figures are already computed, use them rather than calculating):
{table}

Promises made on earlier calls (id, call date, quarters reported after the call, promise, quote). Judge a promise only against quarters listed as reported after its call; if none of them covers the promised period, say too_early:
{promises}

For each id give a verdict. If a promise repeats the same commitment as an earlier id in the list (for example the same margin band restated on a later call), set `same_as` to that earlier id, otherwise null."""

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
                if it.get("speaker") == "analyst" or (doc["kind"] == "concall" and "?" in it["quote"]):
                    continue  # a question from the floor is not management's word (the model's label is checked with a plain rule)
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


MON = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def _ym(label: str) -> tuple[int, int] | None:
    m = re.search(r"([A-Z][a-z]{2})\w*\s+(\d{4})", label)
    return (int(m.group(2)), MON[m.group(1)]) if m and m.group(1) in MON else None


def quarters_after(call_label: str, labels: list[str]) -> list[str]:
    """Quarters whose results came out after a call: any quarter ending in or after the call's month."""
    c = _ym(call_label)
    return [q for q in labels if c and _ym(q) and _ym(q) >= c]


def numbers_ok(evidence: str, tbl: str) -> bool:
    """Every figure of 100 or more quoted in the evidence must appear in the table the judge was given."""
    nums = re.findall(r"\d[\d,]*\.?\d*", evidence)
    big = [n.replace(",", "").rstrip(".") for n in nums if len(n.replace(",", "").split(".")[0]) >= 3]
    flat = tbl.replace(",", "")
    return all(n in flat or n.split(".")[0] in flat for n in big)


def table(co: screener.Company, n: int = 12) -> str:
    """The quarterly table the judge sees. Growth and trailing-year figures are computed here so the model never does the arithmetic."""
    q = co.quarters
    top = co.top_line() or []
    op = q["rows"].get("Operating Profit")
    pat = q["rows"].get("Net Profit")
    lines = ["quarter | revenue | revenue YoY% | revenue last 4 quarters | operating profit | OPM% | net profit | net profit YoY%"]
    for i in range(max(0, len(q["labels"]) - n), len(q["labels"])):
        r = top[i] if top else None
        o = op[i] if op else None
        yoy = f"{(r - top[i - 4]) / top[i - 4] * 100:.1f}" if r is not None and i >= 4 and top[i - 4] else "n/a"
        ttm = f"{sum(top[i - 3:i + 1]):.0f}" if i >= 3 and all(v is not None for v in top[i - 3:i + 1]) else "n/a"
        p, p4 = (pat[i] if pat else None), (pat[i - 4] if pat and i >= 4 else None)
        pyoy = f"{(p - p4) / abs(p4) * 100:.1f}" if p is not None and p4 else "n/a"
        opm = f"{o / r * 100:.1f}" if r and o is not None else "n/a"
        lines.append(f"{q['labels'][i]} | {r} | {yoy} | {ttm} | {o} | {opm} | {p} | {pyoy}")
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
            if d and any(d["norm"][:3000] == o["norm"][:3000] for o in docs):  # the same transcript filed under two dates
                print("  skip duplicate", d["label"])
                continue
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
        tbl = table(co)
        listing = "\n".join(f"{p['id']} | {p['doc'].replace('Concall ', '')} | after: {', '.join(quarters_after(p['doc'], co.quarters['labels'])) or 'none'} | {p['statement']} "
                            f"(target: {p['target']}, horizon: {p.get('horizon')}) | \"{p['quote']}\"" for p in promises)
        j = llm.ask(JUDGE_PROMPT.format(name=co.name, table=tbl, promises=listing), tier="strong", system=JUDGE_SYSTEM, schema=JUDGE_SCHEMA)
        for v in j["data"]["verdicts"]:
            p = by_id.get(v["id"])
            if p:
                verdicts.append({**v, "claim": p["statement"], "target": p.get("target"), "horizon": p.get("horizon"), "quote": p["quote"], "doc": p["doc"],
                                 "page": p["page"], "url": p["url"], "judge": j["model"], "numbers_ok": numbers_ok(v["evidence"], tbl)})
    # one entry per commitment: repeats of the same promise fold into the first one
    first = {v["id"]: v for v in verdicts}
    kept = []
    for v in verdicts:
        tgt = first.get(v.get("same_as") or "")
        if tgt and tgt is not v:
            tgt.setdefault("repeats", []).append({k: v[k] for k in ("doc", "page", "url", "quote")})
        else:
            kept.append(v)
    verdicts = kept
    # business / narrative / bull / bear view, citing ids only
    pool = sorted(items, key=lambda it: (it["type"] != "fact", it["id"]))[:70]
    listing = "\n".join(f"{it['id']} | {it['doc']} | {it['statement']}" for it in pool)
    view = llm.ask(VIEW_PROMPT.format(name=co.name, items=listing), tier="strong", system=VIEW_SYSTEM, schema=VIEW_SCHEMA)
    v, view_model = view["data"], view["model"]

    def section(text, ids):
        """Swap the model's inline ids for footnote numbers in order of appearance; cites list is in the same order."""
        order = []

        def mark(m):
            ns = []
            for i in re.split(r"[,\s]+", m.group(1).strip()):
                if i in by_id:
                    if i not in order:
                        order.append(i)
                    ns.append(order.index(i) + 1)
            return "".join(f"[{n}]" for n in ns)

        text = re.sub(r"\s*\(((?:\d+\.\d+[,\s]*)+)\)", lambda m: " " + mark(m) if mark(m) else "", text)
        for i in ids:  # ids the model listed but did not mark inline still get a footnote
            if i in by_id and i not in order:
                order.append(i)
        return {"text": text, "cites": [{k: by_id[i][k] for k in ("doc", "url", "page", "quote")} for i in order]}

    def cite(ids):
        return section("", ids)["cites"]

    sheet = {
        "symbol": symbol, "name": co.name, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sources": [{"label": d["label"], "url": d["url"], "kind": d["kind"]} for d in docs],
        "business": section(v["business"], v["business_ids"]),
        "narrative": section(v["narrative"], v["narrative_ids"]),
        "balance": section(v["balance"], v["balance_ids"]),
        "bull": [{**section(x["point"], x["ids"]), "point": section(x["point"], x["ids"])["text"]} for x in v["bull"]],
        "bear": [{**section(x["point"], x["ids"]), "point": section(x["point"], x["ids"])["text"]} for x in v["bear"]],
        "promised": verdicts,
        "trajectory": trajectory(co),
        "stats": {"documents": len(docs), "verified_items": len(items), "view_model": view_model,
                  "bulk_model": max({it["model"] for it in items}, key=lambda m: sum(it["model"] == m for it in items)) if items else None},
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
    llm.publish_ledger()
    print(json.dumps(llm.ledger()))


if __name__ == "__main__":
    main()
