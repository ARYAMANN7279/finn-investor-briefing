"""Rule-based filing classifier. Free, instant and deterministic; a model is only asked about the few titles the rules cannot place
(`category == "unclassified"` with `ambiguous=True`).

Categories follow the ENAM reference document. `score` is a base materiality (0 to 100) that says how much an investor should
care about a filing of this kind before looking at anything else; `subtype` separates, e.g., a results *outcome* from a board-meeting
*intimation* of a future date, which are the same category but very different news.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CATEGORIES = ("results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading", "earnings_call",
              "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex", "press_release", "postal_ballot",
              "agm_egm", "pledging", "unclassified")


@dataclass(frozen=True)
class Label:
    category: str
    subtype: str
    score: int
    ambiguous: bool = False


# Order matters: the first matching rule wins, so the specific and the routine rules come before the broad ones.
RULES: list[tuple[str, str, str, int]] = [
    # (pattern on the lower-cased title, category, subtype, score)
    (r"newspaper (publication|clipping)", "unclassified", "newspaper_ad", 4),
    (r"trading window", "unclassified", "trading_window", 3),
    (r"reg\.? ?74|compliance[s]? ?-? ?certificate|iepf|investor education", "unclassified", "compliance", 3),
    (r"esop|espb?s|employee stock|stock option|grant of options", "unclassified", "esop", 4),
    (r"esg rating", "unclassified", "esg", 5),
    (r"board meeting intimation.*(financial results|results)|intimation.*board meeting.*results", "results", "intimation", 52),
    (r"board meeting intimation", "unclassified", "board_intimation", 18),
    (r"report of auditors|limited review|auditor'?s? report", "results", "auditor_report", 38),
    (r"board meeting outcome.*(financial results|results)|outcome of board meeting.*results", "results", "outcome", 92),
    (r"financial results|unaudited.*results|audited.*results|results for the quarter", "results", "outcome", 92),
    (r"investor presentation|results presentation", "results", "deck", 40),
    (r"change in management|appointment of (ceo|cfo|md|chief|managing)|resignation of (ceo|cfo|md|chief|managing)", "management_change", "senior", 84),
    (r"resignation of|cessation|change in directorate|appointment of director|change in director", "management_change", "director", 66),
    (r"earnings? call transcript|transcripts? of|conference call|audio recording", "earnings_call", "transcript", 40),
    (r"analyst.{0,6}investor.{0,5}meet.*outcome", "investor_meetings", "outcome", 20),
    (r"analyst.{0,6}investor.{0,5}meet", "investor_meetings", "intimation", 10),
    (r"acquisition|amalgamation|merger|demerger|joint venture|subsidiary|disinvest|diversification|divest|stake", "M&A", "deal", 80),
    (r"initial public offer|\bipo\b", "fund_raise", "ipo", 76),
    (r"rights issue|qip|preferential|buyback|buy-back|fund raising|debenture|\bncd\b|commercial paper|guarantee", "fund_raise", "financing", 58),
    (r"allotment", "unclassified", "allotment", 12),
    (r"insolvency|cirp|nclt|penalty|show cause|usfda|inspection|litigation|court|tribunal|search and seizure|raid", "litigation", "regulatory", 74),
    (r"credit rating|rating (update|action)|crisil|icra|care ratings|india ratings", "credit_rating", "rating", 48),
    (r"dividend", "dividend", "declared", 60),
    (r"bonus|stock split|sub-?division", "bonus_split", "split", 64),
    (r"capex|capacity expansion|new plant|expansion", "capex", "plan", 70),
    (r"bagging|award of order|receipt of order|order\(s\)|order win|contract", "press_release", "order", 62),
    (r"sast|reg(ulation)?\.? ?29|insider|pit regulations|promoter.*(buy|sell|acquir|dispos)", "insider_trading", "disclosure", 34),
    (r"pledge|encumbrance", "pledging", "pledge", 55),
    (r"postal ballot|e-voting", "postal_ballot", "ballot", 24),
    (r"annual general meeting|extraordinary general meeting|\bagm\b|\begm\b", "agm_egm", "meeting", 24),
    (r"press release|media release|media statement|media statement", "press_release", "release", 44),
    (r"meeting updates|general updates|updates", "unclassified", "update", 15),
]
_COMPILED = [(re.compile(p), c, s, sc) for p, c, s, sc in RULES]


def classify(title: str) -> Label:
    t = re.sub(r"\s+", " ", title.lower())
    for rx, category, subtype, score in _COMPILED:
        if rx.search(t):
            return Label(category, subtype, score)
    return Label("unclassified", "unknown", 12, ambiguous=True)
