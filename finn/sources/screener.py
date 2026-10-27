"""Screener.in company pages: recent filings, quarterly results, annual-report and concall links.

screener.in's robots.txt disallows only query-string URLs, so plain company pages are fetched (cached, one request per company).
Everything here is parsing of one HTML page; `parse_company` is pure and unit-tested.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from .. import net

BASE = "https://www.screener.in"


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _num(cell: str) -> float | None:
    cell = cell.replace(",", "").replace("%", "").strip()
    try:
        return float(cell)
    except ValueError:
        return None


@dataclass
class Company:
    symbol: str
    name: str = ""
    consolidated: bool = True
    ratios: dict[str, str] = field(default_factory=dict)
    quarters: dict = field(default_factory=dict)        # {"labels": [...], "dates": [...], "rows": {"Sales": [...], ...}}
    filings: list[dict] = field(default_factory=list)   # {"title", "url", "time"}
    annual_reports: list[dict] = field(default_factory=list)  # {"label", "url"}
    concalls: list[dict] = field(default_factory=list)  # {"label", "transcript", "ppt"}

    def top_line(self) -> list | None:
        """Quarterly revenue series: industrial companies report "Sales", banks and NBFCs "Revenue"."""
        rows = self.quarters.get("rows", {})
        return rows.get("Sales") or rows.get("Revenue")

    @property
    def is_financial(self) -> bool:
        return "Financing Profit" in self.quarters.get("rows", {})


def _section(page: str, marker: str, length: int = 80000) -> str:
    i = page.find(marker)
    return page[i:i + length] if i >= 0 else ""


def parse_company(page: str, symbol: str) -> Company:
    co = Company(symbol=symbol)
    m = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    co.name = _text(m.group(1)) if m else symbol

    for name, value in re.findall(r'<span class="name">(.*?)</span>\s*<span class="nowrap value">(.*?)</span>\s*</li>', _section(page, 'id="top-ratios"', 6000), re.S):
        co.ratios[_text(name)] = _text(value)

    q = _section(page, 'id="quarters"')
    table = q[q.find("data-result-table"):]
    table = table[: table.find("</table>")]
    dates = re.findall(r'data-date-key="([\d-]+)"', table)
    labels = [_text(x) for x in re.findall(r"<th[^>]*data-date-key[^>]*>(.*?)</th>", table, re.S)]
    rows, pdfs = {}, []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        if len(cells) > 1:
            key = _text(cells[0]).rstrip("+").strip()
            if key == "Raw PDF":  # one link per quarter to the results filing itself
                for c in cells[1:]:
                    m = re.search(r'href="([^"]+)"', c)
                    pdfs.append(urljoin(BASE, html.unescape(m.group(1))) if m else None)
            elif key:
                rows[key] = [_num(_text(c)) for c in cells[1:]]
    co.quarters = {"labels": labels, "dates": dates, "rows": rows, "pdfs": pdfs}

    docs = _section(page, 'id="documents"', 120000)
    ann = docs[docs.find("Announcements"): docs.find("Annual reports")]
    for href, body in re.findall(r'<li[^>]*>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', ann, re.S):
        t = re.search(r'<time datetime="([^"]+)"', body)
        title = _text(body.split("<div")[0])
        if title and t:
            co.filings.append({"title": title, "url": html.unescape(href), "time": t.group(1)})

    ar = docs[docs.find("Annual reports"): docs.find(">Concalls<")]
    for href, label in re.findall(r'<a href="([^"]+)"[^>]*>(Annual Report[^<]*)</a>', ar):
        co.annual_reports.append({"label": _text(label), "url": html.unescape(href)})

    cc = docs[docs.find(">Concalls<"):]
    for li in re.findall(r"<li class=\"flex flex-gap-8[^>]*>(.*?)</li>", cc, re.S):
        label = re.search(r"width: 74px\">([^<]+)<", li)
        if not label:
            continue
        links = {_text(b): html.unescape(h) for h, b in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', li, re.S)}
        if "Transcript" in links or "PPT" in links:
            co.concalls.append({"label": label.group(1).strip(), "transcript": links.get("Transcript"), "ppt": links.get("PPT")})
    return co


def fetch(symbol: str, ttl: float = 6 * 3600) -> Company:
    """Fetch and parse a company page: consolidated view first, standalone if there is no consolidated one."""
    sym = symbol.upper().replace(".NS", "").replace(".BO", "")
    for suffix, consolidated in (("/consolidated/", True), ("/", False)):
        try:
            page = net.get(f"{BASE}/company/{sym}{suffix}", ttl=ttl).decode("utf-8", "replace")
        except net.NotFound:
            continue
        co = parse_company(page, sym)
        if co.top_line():
            co.consolidated = consolidated
            return co
    raise LookupError(f"no Screener page with quarterly results for {sym}")
