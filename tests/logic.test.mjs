import test from "node:test";
import assert from "node:assert/strict";
import { quarterFromTitle, resultsCard, brief, route, priceAlerts, DEFAULT_RULES, effScore } from "../docs/logic.js";

const co = (over = {}) => ({
  symbol: "ACME", name: "Acme Ltd", portfolio: true, financial: false, spark: [1, 2],
  quarters: { labels: ["Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"],
    rows: { Sales: [100, 110, 120, 130, 143], "Operating Profit": [20, 22, 24, 26, 26], "Profit before tax": [15, 16, 18, 20, 22], "Net Profit": [11, 12, 13, 15, 17], Interest: [3, 3, 3, 3, 3] },
    pdfs: [null, null, null, null, "https://x/q.pdf"] },
  stats: [{ date: "2026-10-26", close: 10, move_pct: 5.5, vol_multiple: 2.6 }, { date: "2026-10-23", close: 9, move_pct: 0.4, vol_multiple: 0.9 }],
  filings: [], ...over,
});

test("quarter is read from a results title", () => {
  assert.equal(quarterFromTitle("Financial Results For The Quarter And Half Year Ended September 30, 2026 And Declaration"), "Sep 2026");
  assert.equal(quarterFromTitle("Results for the quarter ended 30Th September, 2026"), "Sep 2026");
  assert.equal(quarterFromTitle("Board Meeting Outcome for Meeting Held On October 10, 2026"), null);
});

test("results card computes QoQ and YoY from the table", () => {
  const r = resultsCard(co(), "Financial Results For The Quarter Ended September 30, 2026");
  const rev = r.rows.find((x) => x.name === "Revenue");
  assert.equal(rev.cur, 143); assert.equal(rev.prev, 130); assert.equal(rev.yago, 100);
  assert.ok(Math.abs(rev.qoq - 10) < 1e-9); assert.ok(Math.abs(rev.yoy - 43) < 1e-9);
  assert.deepEqual(r.rows.map((x) => x.name), ["Revenue", "EBITDA", "PBT", "PAT"]);
  assert.equal(r.pdf, "https://x/q.pdf");
});

test("results card says pending when the table has not caught up", () => {
  const r = resultsCard(co(), "Financial Results For The Quarter Ended December 31, 2026");
  assert.equal(r.pending, true);
});

test("banks get net interest income instead of EBITDA", () => {
  const r = resultsCard(co({ financial: true }), "Results quarter ended September 30, 2026");
  assert.deepEqual(r.rows.map((x) => x.name), ["Revenue", "Net interest income", "PBT", "PAT"]);
  assert.equal(r.rows[1].cur, 140);
});

test("brief windows, ranks and collapses routine filings", () => {
  const f = (title, category, score, time) => ({ title, category, subtype: "x", score, time, url: "u" });
  const data = { built_at: "2026-10-27T12:00:00+05:30", companies: [co({ filings: [
    f("A", "results", 92, "2026-10-26T18:00:00+05:30"), f("B", "unclassified", 4, "2026-10-26T18:00:00+05:30"),
    f("C", "M&A", 80, "2026-10-20T10:00:00+05:30"), f("D", "insider_trading", 34, "2026-10-26T14:00:00+05:30")] })] };
  const day = brief(data, DEFAULT_RULES, 24);
  assert.deepEqual(day.needs.map((x) => x.title), ["A"]);
  assert.deepEqual(day.routine.map((x) => x.title).sort(), ["B", "D"]);
  const week = brief(data, DEFAULT_RULES, 24 * 8);
  assert.deepEqual(week.needs.map((x) => x.title), ["A", "C"]);
  const strict = brief(data, { ...DEFAULT_RULES, bar: 85 }, 24 * 8);
  assert.deepEqual(strict.needs.map((x) => x.title), ["A"]);
});

test("price alerts follow the user's thresholds", () => {
  const ref = new Date("2026-10-27T12:00:00+05:30").getTime();
  const both = priceAlerts([co()], { vol: 2, move: 4 }, ref, 48).map((a) => a.kind).sort();
  assert.deepEqual(both, ["move", "volume"]);
  assert.equal(priceAlerts([co()], { vol: 3, move: 6 }, ref, 48).length, 0);
  assert.equal(priceAlerts([co()], { vol: 2, move: 4 }, ref, 12).length, 0); // session older than the window
});

test("a fresher filing outranks an equal older one", () => {
  const ref = new Date("2026-10-27T12:00:00+05:30").getTime();
  assert.ok(effScore({ score: 80, time: "2026-10-27T06:00:00+05:30" }, ref) > effScore({ score: 80, time: "2026-10-20T06:00:00+05:30" }, ref));
});

test("questions route to a company and a section", () => {
  const cs = [co({ symbol: "INFY", name: "Infosys Ltd" }), co({ symbol: "TCS", name: "Tata Consultancy Services Ltd" }), co({ symbol: "ITC", name: "ITC Ltd" })];
  assert.deepEqual([route("did Infosys deliver on its guidance?", cs).company.symbol, route("did Infosys deliver on its guidance?", cs).section], ["INFY", "promised"]);
  assert.equal(route("how much debt does ITC carry", cs).company.symbol, "ITC");
  assert.equal(route("how much debt does ITC carry", cs).section, "balance");
  assert.equal(route("tell me about something unrelated", cs).company, null);
});

test("several filings about one event collapse into one card", () => {
  const f = (title, subtype, score) => ({ title, category: "results", subtype, score, time: "2026-10-26T18:00:00+05:30", url: title });
  const data = { built_at: "2026-10-27T12:00:00+05:30", companies: [co({ filings: [f("outcome", "outcome", 92), f("board", "outcome", 90), f("auditor", "auditor_report", 38)] })] };
  const r = brief(data, DEFAULT_RULES, 48);
  assert.equal(r.needs.length, 1);
  assert.equal(r.needs[0].title, "outcome");
  assert.deepEqual(r.needs[0].related.map((x) => x.title), ["board"]);
  assert.equal(r.routine.length, 1); // the auditors' report is below the bar
});
