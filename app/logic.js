// Pure functions: no DOM, so they run in the browser and in `node --test`.

export const DEFAULT_RULES = {
  vol: 2.0,          // alert when a day's volume is this many times the 20-session average
  move: 4.0,         // alert when the one-day price move is beyond +/- this percent
  bar: 45,           // filings scoring below this are "routine" and collapsed
  cats: { results: true, "M&A": true, management_change: true, litigation: true, fund_raise: true, credit_rating: true,
          dividend: true, bonus_split: true, capex: true, press_release: true, earnings_call: false, insider_trading: false,
          investor_meetings: false, postal_ballot: false, agm_egm: false, pledging: true, unclassified: false },
};

export const CAT_LABEL = {
  results: "Results", "M&A": "Deal", management_change: "Management", litigation: "Regulatory", fund_raise: "Funding",
  credit_rating: "Rating", dividend: "Dividend", bonus_split: "Bonus/split", capex: "Capex", press_release: "News",
  earnings_call: "Call", insider_trading: "Insider", investor_meetings: "Meetings", postal_ballot: "Ballot", agm_egm: "AGM",
  pledging: "Pledge", unclassified: "Routine",
};

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
export const fmt = (n) => (n == null || Number.isNaN(n) ? "n/a" : inr.format(Math.round(n)));
export const pct = (n, d = 1) => (n == null ? "n/a" : `${n > 0 ? "+" : ""}${n.toFixed(d)}%`);

export const hoursBetween = (ref, iso) => (ref - new Date(iso).getTime()) / 3.6e6;

export function ago(ref, iso) {
  const h = hoursBetween(ref, iso);
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}m ago`;
  if (h < 36) return `${Math.round(h)}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

/** Base score, nudged up for fresh items so that among equals the newest comes first. */
export const effScore = (f, ref) => f.score * (0.88 + 0.12 * Math.exp(-Math.max(0, hoursBetween(ref, f.time)) / 48));

const MONTHS = { january: "Jan", february: "Feb", march: "Mar", april: "Apr", may: "May", june: "Jun", july: "Jul", august: "Aug",
  september: "Sep", october: "Oct", november: "Nov", december: "Dec" };

/** "... Quarter And Half Year Ended September 30, 2026 ..." -> "Sep 2026" (the label Screener's table uses). */
export function quarterFromTitle(title) {
  const m = /ended\s+(?:on\s+)?(?:\d{1,2}\s*(?:st|nd|rd|th)?\s+)?([A-Za-z]+)\s*(?:\d{1,2}\s*(?:st|nd|rd|th)?)?,?\s*(\d{4})/i.exec(title);
  return m && MONTHS[m[1].toLowerCase()] ? `${MONTHS[m[1].toLowerCase()]} ${m[2]}` : null;
}

const change = (cur, base) => (cur == null || base == null || base <= 0 ? null : ((cur - base) / base) * 100);

/**
 * Headline numbers for the results card: this quarter against the previous quarter (QoQ) and the same quarter a year ago (YoY).
 * EBITDA is Screener's operating profit (sales less operating expenses, before other income, interest and depreciation).
 * Banks and NBFCs have no EBITDA, so they get net interest income (revenue less interest paid) instead.
 */
export function resultsCard(co, title) {
  const q = co.quarters;
  const want = quarterFromTitle(title) || q.labels[q.labels.length - 1];
  const i = q.labels.indexOf(want);
  if (i < 0) return { pending: true, quarter: want, why: `Screener's table does not have ${want} yet.` };
  const [mon, yr] = want.split(" ");
  let y = q.labels.indexOf(`${mon} ${Number(yr) - 1}`);
  const r = q.rows;
  const top = r.Sales || r.Revenue;
  const series = co.financial
    ? [["Revenue", top], ["Net interest income", top && r.Interest ? top.map((v, k) => (v == null || r.Interest[k] == null ? null : v - r.Interest[k])) : null],
       ["PBT", r["Profit before tax"]], ["PAT", r["Net Profit"]]]
    : [["Revenue", top], ["EBITDA", r["Operating Profit"]], ["PBT", r["Profit before tax"]], ["PAT", r["Net Profit"]]];
  const rows = series.filter(([, s]) => s).map(([name, s]) => ({
    name, cur: s[i], prev: i > 0 ? s[i - 1] : null, yago: y >= 0 ? s[y] : null,
    qoq: i > 0 ? change(s[i], s[i - 1]) : null, yoy: y >= 0 ? change(s[i], s[y]) : null,
  }));
  return { pending: false, quarter: want, prevLabel: i > 0 ? q.labels[i - 1] : null, yagoLabel: y >= 0 ? q.labels[y] : null, rows,
           pdf: (q.pdfs || [])[i] || null, financial: !!co.financial };
}

const WHY = {
  "results/outcome": "Results are out. Tap for the headline numbers against last quarter and last year.",
  "results/intimation": "Board meets to approve results. The numbers are still to come.",
  "results/auditor_report": "Auditors' report on the results.",
  "results/deck": "Management's results presentation.",
  "management_change/senior": "A change at the top. Who leaves, who comes in, and when.",
  "management_change/director": "A board-level change. Usually less urgent than a CEO or CFO move.",
  "M&A/deal": "Corporate action: an acquisition, a new subsidiary or a stake sale. Check the terms.",
  "fund_raise/ipo": "A public offering is moving. It changes how much of the business you own.",
  "fund_raise/financing": "Money going in or out: debt, buybacks or guarantees.",
  "litigation/regulatory": "A regulator, a court or an inspector is involved.",
  "credit_rating/rating": "A rating agency has acted. Check whether it is an upgrade or a downgrade.",
  "dividend/declared": "A cash payout. Note the record date.",
  "earnings_call/transcript": "Call material is out. Ask FINN whether management delivered on what it promised.",
  "press_release/order": "An order or contract win. Look at the size against annual revenue.",
  "press_release/release": "Company news in management's own words.",
  "insider_trading/disclosure": "A holder crossed or changed a shareholding threshold.",
};
export const why = (f) => WHY[`${f.category}/${f.subtype}`] || WHY[f.category] || (f.ambiguous ? "Unusual title. Worth a quick look." : "Routine paperwork.");

const stamp = (d) => new Date(`${d}T15:30:00+05:30`).getTime();

/** Volume and price alerts inside the window, newest session per company and kind. */
export function priceAlerts(companies, rules, ref, hours) {
  const out = [];
  for (const co of companies) {
    const seen = new Set();
    for (const s of [...co.stats].reverse()) {
      if ((ref - stamp(s.date)) / 3.6e6 > hours || stamp(s.date) > ref) continue;
      if (s.vol_multiple >= rules.vol && !seen.has("v")) { seen.add("v"); out.push({ symbol: co.symbol, kind: "volume", date: s.date, vol: s.vol_multiple, move: s.move_pct, spark: co.spark }); }
      if (Math.abs(s.move_pct) >= rules.move && !seen.has("m")) { seen.add("m"); out.push({ symbol: co.symbol, kind: "move", date: s.date, vol: s.vol_multiple, move: s.move_pct, spark: co.spark }); }
    }
  }
  return out.sort((a, b) => Math.abs(b.move) + b.vol - (Math.abs(a.move) + a.vol));
}

/** The Brief: what needs you, what is routine, and which price alerts fired, for a window in hours. */
export function brief(data, rules, hours) {
  const ref = new Date(data.built_at).getTime();
  const mine = data.companies.filter((c) => c.portfolio);
  const items = [];
  for (const co of mine) for (const f of co.filings) {
    if (hoursBetween(ref, f.time) > hours) continue;
    items.push({ ...f, symbol: co.symbol, name: co.name, eff: effScore(f, ref), wanted: !!rules.cats[f.category] && f.score >= rules.bar });
  }
  items.sort((a, b) => b.eff - a.eff);
  // One event often files several documents (results, board outcome, auditors' report). Show the strongest and fold the rest into it.
  const needs = [], seen = new Map();
  for (const x of items.filter((y) => y.wanted)) {
    const key = `${x.symbol}|${x.category}`;
    if (seen.has(key)) seen.get(key).related.push(x); else { const g = { ...x, related: [] }; seen.set(key, g); needs.push(g); }
  }
  return { ref, needs, routine: items.filter((x) => !x.wanted), alerts: priceAlerts(mine, rules, ref, hours), total: items.length };
}

const SECTION_WORDS = {
  guidance: ["guid", "promis", "deliver", "outlook", "target", "said", "claim"],
  narrative: ["narrative", "story", "diverge", "agree", "tone"],
  balance: ["debt", "leverage", "balance", "borrow", "working capital", "funding", "liabilit"],
  cash: ["cash", "fcf", "conversion", "capex"],
  trajectory: ["trajectory", "trend", "growth", "grow", "margin", "years", "direction"],
  financial: ["financial", "revenue", "profit", "pat", "ebitda", "ratio", "numbers"],
  business: ["business", "segment", "what does", "mix", "does the company"],
  bullbear: ["bull", "bear", "risk", "buy", "case", "upside", "downside"],
};
const SECTION_ID = { guidance: "promised", narrative: "narrative", balance: "balance", cash: "cash", trajectory: "trajectory", financial: "financial", business: "business", bullbear: "bullbear" };

/** Turns a question into {company, section}: "did Infosys deliver on guidance?" -> INFY, promised-vs-delivered. */
export function route(query, companies) {
  const q = query.toLowerCase();
  let best = null;
  for (const c of companies) {
    const names = [c.symbol.toLowerCase(), c.name.toLowerCase().replace(/\b(ltd|limited|industries|india|corporation|corp)\b\.?/g, "").trim()];
    for (const n of names) {
      if (n && new RegExp(`(^|[^a-z])${n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^a-z]|$)`).test(q)) { if (!best || n.length > best.len) best = { c, len: n.length }; }
    }
  }
  let section = null, hits = 0;
  for (const [k, words] of Object.entries(SECTION_WORDS)) {
    const h = words.filter((w) => q.includes(w)).length;
    if (h > hits) { hits = h; section = SECTION_ID[k]; }
  }
  return { company: best ? best.c : null, section };
}
