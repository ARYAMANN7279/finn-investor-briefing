"""Reads the snapshot, runs the model over the filings that matter, writes docs/data/enrich.json (keyed by filing URL).

    python3 -m finn.enrich            # results, management changes, one-line summaries
Everything is cached by request, so re-running costs nothing for documents already read.
"""
from __future__ import annotations

import json
import pathlib
import sys

from . import extract, llm, pdftext

SNAP = pathlib.Path(__file__).resolve().parent.parent / "docs" / "data" / "snapshot.json"

PEOPLE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "people": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "name": {"type": "STRING"}, "action": {"type": "STRING", "enum": ["appointed", "resigned", "retiring", "reappointed", "role_change", "other"]},
            "role": {"type": "STRING"}, "effective": {"type": "STRING", "nullable": True},
            "reason": {"type": "STRING", "nullable": True}, "bio": {"type": "STRING", "nullable": True}},
            "required": ["name", "action", "role"]}},
    },
    "required": ["summary", "people"],
}
PEOPLE_SYSTEM = ("You summarise Indian stock-exchange filings about management and board changes for a retail investor. "
                 "Use only what the filing text says. Never add outside knowledge about a person. If the filing gives a profile "
                 "(education, experience, years in the company) put a short version in `bio`, else set bio to null.")
PEOPLE_PROMPT = """Filing title: "{title}" (company: {name}).
Write `summary` as two plain sentences: who is leaving or joining, in which role, from when, and why if stated.
List every person named in the change in `people`.

FILING TEXT:
{text}"""

LINE_SCHEMA = {"type": "OBJECT", "properties": {"line": {"type": "STRING"}}, "required": ["line"]}
LINE_SYSTEM = "You write one-sentence summaries of Indian stock-exchange filings for a retail investor. Plain words, include the key number or date. Use only the filing text."
LINE_PROMPT = 'Filing title: "{title}" (company: {name}).\nOne sentence, at most 28 words.\n\nFILING TEXT:\n{text}'


def _text(url: str, limit: int = 14000) -> str:
    return "\n".join(pdftext.pages(url))[:limit]


def refresh_checks(snapshot: dict, db: dict) -> int:
    """Recompute saved filing-vs-Screener checks after validation logic changes, without another model call."""
    updated = 0
    for co in snapshot.get("companies", []):
        q = co["quarters"]
        for filing in co.get("filings", []):
            if filing.get("category") != "results" or filing.get("subtype") != "outcome":
                continue
            row = db.get(filing["url"])
            if not row or row.get("kind") != "results" or row.get("status") != "extracted":
                continue
            check = extract.cross_check(row["data"], q["labels"], q["rows"], extract.quarter_label(filing["title"]) or "", co["financial"])
            if row.get("check") != check:
                row["check"] = check
                updated += 1
    if updated:
        extract.save(db)
    return updated


def main() -> None:
    snap = json.loads(SNAP.read_text())
    db = extract.load()
    refreshed = refresh_checks(snap, db)
    if refreshed:
        print("refreshed", refreshed, "saved results cross-checks")
    todo = []
    for co in snap["companies"]:
        if not co["portfolio"]:
            continue
        for f in co["filings"]:
            if f["category"] == "results" and f["subtype"] == "outcome":
                todo.append(("results", co, f))
            elif f["category"] == "management_change":
                todo.append(("people", co, f))
            elif f["score"] >= 45 and f["category"] not in ("results", "unclassified"):
                todo.append(("line", co, f))
    print(len(todo), "filings to read")
    for kind, co, f in todo:
        key = f["url"]
        if key in db and db[key].get("kind") == kind and db[key].get("state") != "error":
            continue
        try:
            if kind == "results":
                r = extract.extract_results(key, f["title"])
                row = {"kind": kind, **r}
                if r["status"] == "extracted":
                    q = co["quarters"]
                    row["check"] = extract.cross_check(r["data"], q["labels"], q["rows"], extract.quarter_label(f["title"]) or "", co["financial"])
            elif kind == "people":
                r = llm.ask(PEOPLE_PROMPT.format(title=f["title"], name=co["name"], text=_text(key)), system=PEOPLE_SYSTEM, schema=PEOPLE_SCHEMA)
                row = {"kind": kind, "model": r["model"], **r["data"]}
            else:
                r = llm.ask(LINE_PROMPT.format(title=f["title"], name=co["name"], text=_text(key, 8000)), system=LINE_SYSTEM, schema=LINE_SCHEMA)
                row = {"kind": kind, "model": r["model"], "line": r["data"]["line"]}
        except Exception as err:  # keep going; the app falls back to the rule-based text
            row = {"kind": kind, "state": "error", "why": str(err)[:200]}
        db[key] = {**row, "symbol": co["symbol"]}
        extract.save(db)
        print(co["symbol"], kind, db[key].get("state") or db[key].get("status") or "ok", db[key].get("check", {}).get("state", ""))
    llm.publish_ledger()
    print(json.dumps(llm.ledger()))


if __name__ == "__main__":
    sys.exit(main())
