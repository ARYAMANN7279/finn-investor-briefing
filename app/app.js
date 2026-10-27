import { DEFAULT_RULES, CAT_LABEL, fmt, pct, ago, why, brief, resultsCard, route } from "./logic.js";

const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const store = {
  get(k, d) { try { const v = localStorage.getItem("finn2." + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("finn2." + k, JSON.stringify(v)); } catch { /* private mode: keep going */ } },
};

const state = {
  data: null, enrich: {}, ledger: {}, research: { index: {}, sheets: {} },
  tab: store.get("tab", "brief"),
  hours: store.get("hours", 24), custom: store.get("custom", false),
  rules: { ...DEFAULT_RULES, ...store.get("rules", {}), cats: { ...DEFAULT_RULES.cats, ...(store.get("rules", {}).cats || {}) } },
  open: new Set(), showRoutine: false, ask: { q: "", symbol: null, section: null, msg: "" },
};
const save = () => { store.set("tab", state.tab); store.set("hours", state.hours); store.set("custom", state.custom); store.set("rules", state.rules); };

async function getJSON(url) { try { const r = await fetch(url); return r.ok ? await r.json() : null; } catch { return null; } }

const spark = (arr, cls = "") => {
  if (!arr || arr.length < 2) return "";
  const lo = Math.min(...arr), hi = Math.max(...arr), w = 64, h = 22;
  const pts = arr.map((v, i) => `${(i / (arr.length - 1)) * w},${h - 2 - ((v - lo) / (hi - lo || 1)) * (h - 4)}`);
  const up = arr[arr.length - 1] >= arr[0];
  return `<svg class="spark ${cls || (up ? "up" : "down")}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="M${pts.join("L")}"/></svg>`;
};

const byCo = () => Object.fromEntries(state.data.companies.map((c) => [c.symbol, c]));
const winLabel = () => (state.hours % 24 === 0 ? (state.hours === 24 ? "24 hours" : `${state.hours / 24} days`) : `${state.hours} hours`);

/* ---------------------------------------------------------------- Brief */

const modelName = (m) => (m || "").replace(/^gemini-/, "Gemini ").replace(/-/g, " ");

function checkHTML(f) {
  const c = state.enrich[f.url]?.check;
  if (!c) return `<span class="badge">numbers from Screener only</span>`;
  if (c.state === "verified") return `<span class="badge ok">✓ filing and Screener agree</span>`;
  if (c.state === "mismatch") {
    const bad = c.detail.filter((d) => d.ok === false).map((d) => `${d.metric.replace(/_/g, " ")}: filing ${fmt(d.filing)}, Screener ${fmt(d.screener)}`).join("; ");
    return `<span class="badge warn">filing and Screener differ</span> <span class="note">${esc(bad)}. Check the filing.</span>`;
  }
  return `<span class="badge">could not cross-check</span>`;
}

function resultsHTML(co, f) {
  const r = resultsCard(co, f.title);
  if (r.pending) return `<p class="why">${esc(r.why)} Open the filing for the numbers.</p>`;
  const cell = (v) => (v == null ? "n/a" : `<span class="${v >= 0 ? "up" : "down"}">${pct(v)}</span>`);
  const body = r.rows.map((x) => `<tr><td>${esc(x.name)}</td><td>${fmt(x.cur)}</td><td>${cell(x.qoq)}</td><td>${cell(x.yoy)}</td></tr>`).join("");
  const e = state.enrich[f.url];
  return `<table class="nums"><thead><tr><th>₹ crore, ${esc(r.quarter)}</th><th>Now</th><th>QoQ vs ${esc(r.prevLabel || "-")}</th><th>YoY vs ${esc(r.yagoLabel || "-")}</th></tr></thead><tbody>${body}</tbody></table>
    <p style="margin:8px 0 0">${checkHTML(f)}</p>
    <p class="note">${r.financial ? "Banks and NBFCs have no EBITDA; net interest income is shown instead." : "EBITDA is operating profit: sales less operating costs, before other income, interest and depreciation."} ${e?.check ? `${esc(modelName(e.model))} read revenue, PBT and PAT out of the filing and they were compared with Screener's table (1.5% tolerance). ` : ""}${r.pdf ? `<a class="link" href="${esc(r.pdf)}" target="_blank" rel="noopener">Results filing</a>` : ""}</p>`;
}

const ACTION = { appointed: "Joins", resigned: "Leaves", retiring: "Retiring", reappointed: "Re-appointed", role_change: "New role", other: "Change" };

function enrichHTML(f) {
  const e = state.enrich[f.url];
  if (!e || e.state === "error") return "";
  if (e.kind === "line") return `<p class="note">One-line summary by ${esc(modelName(e.model))}, from the filing text.</p>`;
  if (e.kind !== "people") return "";
  const people = (e.people || []).map((p) => `<div class="person"><div><b>${esc(p.name)}</b> <span class="badge">${esc(ACTION[p.action] || "Change")}</span></div>
    <div class="why">${esc(p.role)}${p.effective ? ` · from ${esc(p.effective)}` : ""}${p.reason ? ` · ${esc(p.reason)}` : ""}</div>
    ${p.bio ? `<blockquote>${esc(p.bio)}</blockquote><div class="note">Background as stated in the filing.</div>` : `<div class="note">The filing gives no background for this person. FINN does not look people up elsewhere.</div>`}</div>`).join("");
  return `${people}<p class="note">Summary by ${esc(modelName(e.model))}, from the filing text.</p>`;
}

function card(f, co) {
  const open = state.open.has(f.url);
  const hot = f.eff > 75;
  const body = f.category === "results" && f.subtype === "outcome" ? resultsHTML(co, f) : "";
  const e = state.enrich[f.url];
  const lead = e && e.state !== "error" ? e.line || e.summary : "";
  return `<article class="card ${hot ? "hot" : ""}" aria-expanded="${open}" data-url="${esc(f.url)}">
    <button class="go" data-act="toggle" aria-label="Show details"></button>
    <div class="row"><span class="sym">${esc(f.symbol)}</span><span class="tag k-${esc(f.category)}">${esc(CAT_LABEL[f.category] || f.category)}</span>${f.related?.length ? `<span class="tag">+${f.related.length} related</span>` : ""}<span class="when">${ago(state.ref, f.time)}</span></div>
    <div class="title">${esc(f.title.replace(/^Announcement under Regulation 30 \(LODR\)\s*-\s*/i, ""))}</div>
    <div class="why">${esc(lead || why(f))}</div>
    <div class="meter" title="Materiality ${Math.round(f.eff)}"><i style="width:${Math.min(100, f.eff)}%"></i></div>
    <div class="more">${enrichHTML(f)}${body}${(f.related || []).map((r) => `<p class="note" style="margin:6px 0 0">Also filed: <a class="link" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title.replace(/^Announcement under Regulation 30 \(LODR\)\s*-\s*/i, "").slice(0, 90))}</a></p>`).join("")}<p style="margin:8px 0 0"><a class="link" href="${esc(f.url)}" target="_blank" rel="noopener">Open the filing (PDF)</a></p></div>
  </article>`;
}

function briefList() {
  const b = brief(state.data, state.rules, state.hours);
  state.ref = b.ref;
  const cos = byCo();
  const alerts = b.alerts.length ? `<div class="h">Unusual moves<span class="n">${b.alerts.length}</span></div><div class="alerts">${b.alerts.slice(0, 6).map((a) =>
    `<div class="alert">${spark(a.spark, "flat")}<span><b>${esc(a.symbol)}</b> ${a.kind === "volume" ? `volume ${a.vol.toFixed(1)}× its 20-day average` : `moved ${pct(a.move)}`}</span><span class="why">${esc(new Date(a.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" }))}</span></div>`).join("")}</div>` : "";
  const needs = b.needs.length ? b.needs.map((f) => card(f, cos[f.symbol])).join("")
    : `<div class="empty"><b>Nothing needs you.</b>${b.total} filings came in; none cleared your bar. Lower it in Watch if you want more.</div>`;
  const routine = b.routine.length ? `<button class="fold" data-act="routine"><b>${b.routine.length} routine</b> filings ${state.showRoutine ? "shown" : "hidden"}. Tap to ${state.showRoutine ? "hide" : "peek"}.</button>
    <div class="routine ${state.showRoutine ? "on" : ""}">${b.routine.map((f) => `<div class="r"><b>${esc(f.symbol)}</b><a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.title.replace(/^Announcement under Regulation 30 \(LODR\)\s*-\s*/i, ""))}</a></div>`).join("")}</div>` : "";
  return `<div class="lead">${b.needs.length ? `${b.needs.length} need${b.needs.length === 1 ? "s" : ""} you` : "All quiet"}</div>
    <div class="sub">Last ${winLabel()} · ${b.total} filings across ${state.data.companies.filter((c) => c.portfolio).length} holdings</div>${alerts}<div class="h">Needs you<span class="n">${b.needs.length}</span></div>${needs}<div class="h"></div>${routine}`;
}

function viewBrief() {
  const chips = [[24, "24 h"], [72, "3 days"], [168, "7 days"]].map(([h, l]) => `<button class="chip" data-act="win" data-h="${h}" aria-pressed="${!state.custom && state.hours === h}">${l}</button>`).join("")
    + `<button class="chip" data-act="custom" aria-pressed="${state.custom}">Custom</button>`;
  const slider = state.custom ? `<div class="rule"><div class="s">Last <b>${winLabel()}</b></div><input type="range" min="6" max="240" step="6" value="${state.hours}" data-act="hours" aria-label="Window in hours"><div class="hint">The exchange feed shows each company's latest filings, about ten days back.</div></div>` : "";
  return `<div class="chips" style="margin-top:0">${chips}</div>${slider}<div id="blist">${briefList()}</div>`;
}

/* ---------------------------------------------------------------- Ask */

const SECTIONS = [["promised", "Promised vs delivered", true], ["business", "Business"], ["trajectory", "Trajectory (reported numbers)"],
  ["balance", "Balance sheet and cash"], ["narrative", "Narrative vs numbers"], ["bullbear", "Bull vs bear"]];

const VERDICT = { delivered: "Delivered", partly: "Partly", missed: "Missed", too_early: "Too early", not_measurable: "Not testable" };
const ORDER = ["missed", "partly", "delivered", "too_early", "not_measurable"];

function sources(cites) {
  if (!cites || !cites.length) return "";
  return `<details class="src"><summary>${cites.length} source${cites.length === 1 ? "" : "s"}</summary><ol>${cites.map((c) => `<li><blockquote>“${esc(c.quote)}”</blockquote><a class="link" href="${esc(c.url)}#page=${c.page}" target="_blank" rel="noopener">${esc(c.doc)}, page ${c.page}</a></li>`).join("")}</ol></details>`;
}
const withNotes = (t) => esc(t).replace(/\[(\d+)\]/g, '<sup class="fn">$1</sup>');
const prose = (x) => (x && x.text ? `<p style="margin-top:0">${withNotes(x.text)}</p>${sources(x.cites)}` : `<p class="why">Not covered by this sheet.</p>`);

function sectionBody(sheet, id) {
  if (id === "promised") {
    const rows = [...(sheet.promised || [])].sort((a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict));
    if (!rows.length) return `<p class="why">Not enough quantified guidance in the transcripts to compare.</p>`;
    const n = (v) => rows.filter((p) => p.verdict === v).length;
    const head = `<p class="why" style="margin-top:0">${rows.length} commitments from earlier calls, tested against the quarters reported since: ${n("delivered")} delivered, ${n("partly")} partly, ${n("missed")} missed, ${n("too_early")} too early, ${n("not_measurable")} not testable from results numbers (volumes, projects, programmes).</p>`;
    return head + rows.map((p) => `<div class="pvd"><div class="q">${esc(p.doc)} <span class="verdict v-${esc(p.verdict)}">${esc(VERDICT[p.verdict] || p.verdict)}</span></div>
      <div class="said"><b>Said:</b> ${esc(p.claim)}</div><div class="got"><b>What followed:</b> ${esc(p.evidence)}${p.numbers_ok === false ? ` <span class="badge warn">a figure here is not in the table, check it</span>` : ""}</div>
      <blockquote>“${esc(p.quote)}”</blockquote><a class="link" href="${esc(p.url)}#page=${p.page}" target="_blank" rel="noopener">${esc(p.doc)}, page ${p.page}</a>
      ${(p.repeats || []).length ? `<div class="note">Said again: ${p.repeats.map((r) => `<a class="link" href="${esc(r.url)}#page=${r.page}" target="_blank" rel="noopener">${esc(r.doc)}, p.${r.page}</a>`).join(", ")}</div>` : ""}</div>`).join("");
  }
  if (id === "bullbear") {
    const li = (a) => a.map((x) => `<li>${withNotes(x.point)}${sources(x.cites)}</li>`).join("");
    return `<div class="cols"><div><h4 class="up">Bull</h4><ul>${li(sheet.bull || [])}</ul></div><div><h4 class="down">Bear</h4><ul>${li(sheet.bear || [])}</ul></div></div>`;
  }
  if (id === "trajectory") {
    const t = sheet.trajectory;
    if (!t || !t.rows) return `<p class="why">No quarterly table available.</p>`;
    const rows = t.rows.slice(-8);
    const vals = t.rows.map((r) => r.revenue).filter((v) => v != null);
    return `${vals.length > 2 ? `<div style="margin:0 0 6px">${spark(vals)} <span class="note">Revenue, last ${vals.length} quarters</span></div>` : ""}
      <table class="nums"><thead><tr><th>Quarter</th><th>Revenue ₹ cr</th><th>YoY</th><th>${t.financial ? "" : "Op. margin"}</th><th>Net profit</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.q)}</td><td>${fmt(r.revenue)}</td><td>${r.rev_yoy == null ? "n/a" : `<span class="${r.rev_yoy >= 0 ? "up" : "down"}">${pct(r.rev_yoy)}</span>`}</td><td>${t.financial || r.opm == null ? "" : `${r.opm}%`}</td><td>${fmt(r.pat)}</td></tr>`).join("")}</tbody></table>
      <p class="note">Plain arithmetic on the company's reported quarterly table. No model involved.</p>`;
  }
  return prose(sheet[id]);
}

function sheetHTML(sheet, focus) {
  const st = sheet.stats || {};
  const secs = SECTIONS.map(([id, label, hero]) => `<section class="sec ${hero ? "hero" : ""}" aria-expanded="${focus ? focus === id : !!hero}" data-sec="${id}"><button data-act="sec">${esc(label)}<span class="chev">›</span></button><div class="body">${sectionBody(sheet, id)}</div></section>`).join("");
  return `<div class="sheet"><h2>${esc(sheet.name || sheet.symbol)}</h2>
    <p class="note" style="margin-top:2px">Built only from the company's own annual report and concall transcripts (${(sheet.sources || []).length} documents, ${st.verified_items || 0} quotes checked word for word against the PDFs). ${st.bulk_model ? `Extraction: ${esc(modelName(st.bulk_model))}. ` : ""}${st.view_model ? `Comparison and writing: ${esc(modelName(st.view_model))}.` : ""}</p>${secs}
    <div class="h">Documents</div>${(sheet.sources || []).map((s) => `<p class="why" style="margin:2px 0"><a class="link" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a></p>`).join("")}</div>`;
}

function viewAsk() {
  const have = Object.keys(state.research.index);
  const sug = have.slice(0, 3).map((s) => `Did ${byCo()[s]?.name.replace(/ Ltd\.?$/i, "") || s} deliver on its guidance?`);
  const { q, symbol, section, msg } = state.ask;
  let out = "";
  if (msg) out = `<div class="empty"><b>${esc(msg)}</b></div>`;
  else if (symbol) {
    const sheet = state.research.sheets[symbol];
    out = sheet ? sheetHTML(sheet, section) : `<div class="card"><div class="title">${esc(byCo()[symbol]?.name || symbol)}: no research sheet prepared yet</div><div class="why">Build one with the engine, which works for any NSE ticker:<br><code>python3 -m finn.research ${esc(symbol)}</code></div></div>`;
  } else out = `<div class="lead">Ask about a company</div><p class="sub">Type a question or a ticker. FINN answers from annual reports and concall transcripts only.</p>
    ${have.length ? `<div class="chips">${sug.map((s) => `<button class="chip" data-act="try" data-q="${esc(s)}">${esc(s)}</button>`).join("")}</div><p class="note">Prepared sheets: ${have.map(esc).join(", ")}. Any other NSE ticker can be built with <code>python3 -m finn.research TICKER</code>.</p>` : `<p class="note">No sheets built yet. Run <code>python3 -m finn.research TICKER</code>.</p>`}`;
  return `<form class="ask" data-act="ask" autocomplete="off"><input name="q" value="${esc(q)}" placeholder="e.g. did Infosys deliver on its guidance?" enterkeyhint="send" aria-label="Ask FINN"><button type="submit">Ask</button></form>${out}`;
}

async function runAsk(q) {
  const cos = state.data.companies;
  const r = route(q, cos);
  state.ask = { q, symbol: null, section: r.section, msg: "" };
  if (!r.company) { state.ask.msg = "Name a company or ticker, for example “ITC debt” or “TCS guidance”."; return; }
  state.ask.symbol = r.company.symbol;
  if (state.research.index[r.company.symbol] && !state.research.sheets[r.company.symbol]) {
    state.research.sheets[r.company.symbol] = await getJSON(`data/research/${r.company.symbol}.json`);
  }
}

/* ---------------------------------------------------------------- Watch */

function viewWatch() {
  const r = state.rules;
  const L = Object.entries(state.ledger);
  const calls = L.reduce((n, [, x]) => n + x.calls, 0), hits = L.reduce((n, [, x]) => n + x.cache_hits, 0);
  const tok = L.reduce((n, [, x]) => n + x.input_tokens + x.output_tokens, 0);
  const cats = Object.keys(DEFAULT_RULES.cats).filter((k) => k !== "unclassified").map((k) => `<button class="chip" data-act="cat" data-k="${esc(k)}" aria-pressed="${!!r.cats[k]}">${esc(CAT_LABEL[k])}</button>`).join("");
  const hold = state.data.companies.filter((c) => c.portfolio).map((c) => {
    const s = c.stats[c.stats.length - 1];
    const flag = s.vol_multiple >= r.vol || Math.abs(s.move_pct) >= r.move;
    return `<div class="hold ${flag ? "flag" : ""}">${spark(c.spark)}<div class="nm"><div class="sym">${esc(c.symbol)}</div><div>${esc(c.sector)}</div></div><div class="px">₹${fmt(c.last.close)}<br><span class="${s.move_pct >= 0 ? "up" : "down"}">${pct(s.move_pct, 2)}</span> · ${s.vol_multiple.toFixed(1)}×</div></div>`;
  }).join("");
  return `<div class="lead">Your rules</div><p class="sub">You decide what is unusual. The Brief re-ranks the moment you move a slider.</p>
    <div class="h">Alert me when</div>
    <div class="rule"><div class="s">Volume is above <b>${r.vol.toFixed(1)}×</b> its 20-day average</div><input type="range" min="1.2" max="5" step="0.1" value="${r.vol}" data-act="vol" aria-label="Volume multiple"></div>
    <div class="rule"><div class="s">Price moves beyond <b>±${r.move.toFixed(1)}%</b> in a day</div><input type="range" min="1" max="10" step="0.5" value="${r.move}" data-act="move" aria-label="Price move percent"></div>
    <div class="rule"><div class="s">A filing scores at least <b>${r.bar}</b> out of 100</div><input type="range" min="10" max="90" step="5" value="${r.bar}" data-act="bar" aria-label="Materiality bar"><div class="hint">Below this, filings are collapsed as routine.</div></div>
    <div class="h">I care about</div><div class="chips" style="margin-top:0">${cats}</div>
    <div class="h">Holdings<span class="n">price · today vs average volume</span></div>${hold}
    <div class="h">Model spend</div><div class="cost"><div><b>${tok >= 1000 ? `${Math.round(tok / 1000)}k` : tok}</b><span>tokens</span></div><div><b>${calls}</b><span>model calls</span></div><div><b>${hits}</b><span>cache hits</span></div></div>
    ${L.map(([m, x]) => `<p class="note" style="margin:2px 0">${esc(modelName(m))}: ${x.calls} calls, ${Math.round((x.input_tokens + x.output_tokens) / 1000)}k tokens</p>`).join("")}
    <p class="note">Free tier, so $0 spent. A small model reads the documents, a stronger one is used only for the promised-versus-delivered comparison and the written view, and every request is cached so a document is paid for once.</p>`;
}

/* ---------------------------------------------------------------- shell */

const VIEWS = { brief: viewBrief, ask: viewAsk, watch: viewWatch };

function render(keepScroll = true) {
  const y = window.scrollY;
  $("#view").innerHTML = VIEWS[state.tab]();
  for (const b of document.querySelectorAll(".tabs button")) b.setAttribute("aria-current", b.dataset.tab === state.tab ? "page" : "false");
  if (keepScroll) window.scrollTo(0, y);
}

function header() {
  const d = new Date(state.data.built_at);
  $("#asof").textContent = `as of ${d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false })} IST`;
  const movers = state.data.companies.filter((c) => c.portfolio).map((c) => [c.symbol, c.stats[c.stats.length - 1].move_pct])
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 7);
  $("#pulse").innerHTML = movers.map(([s, m]) => `<span class="ticker"><b>${esc(s)}</b><span class="${m >= 0 ? "up" : "down"}">${pct(m, 2)}</span></span>`).join("");
}

document.addEventListener("click", async (e) => {
  const t = e.target.closest("[data-act], .tabs button");
  if (!t) return;
  if (t.dataset.tab) { state.tab = t.dataset.tab; save(); render(false); window.scrollTo(0, 0); return; }
  const a = t.dataset.act;
  if (a === "toggle") { const u = t.closest(".card").dataset.url; state.open.has(u) ? state.open.delete(u) : state.open.add(u); render(); }
  else if (a === "win") { state.hours = +t.dataset.h; state.custom = false; save(); render(); }
  else if (a === "custom") { state.custom = !state.custom; save(); render(); }
  else if (a === "routine") { state.showRoutine = !state.showRoutine; render(); }
  else if (a === "cat") { state.rules.cats[t.dataset.k] = !state.rules.cats[t.dataset.k]; save(); render(); }
  else if (a === "sec") { const s = t.closest(".sec"); s.setAttribute("aria-expanded", s.getAttribute("aria-expanded") !== "true"); }
  else if (a === "try") { await runAsk(t.dataset.q); render(false); window.scrollTo(0, 0); }
});

document.addEventListener("input", (e) => {
  const t = e.target, a = t.dataset?.act;
  if (!["vol", "move", "bar", "hours"].includes(a)) return;
  if (a === "hours") state.hours = +t.value; else state.rules[a] = +t.value;
  save();
  const label = t.closest(".rule").querySelector("b");
  label.textContent = a === "vol" ? `${(+t.value).toFixed(1)}×` : a === "move" ? `±${(+t.value).toFixed(1)}%` : a === "bar" ? t.value : winLabel();
  if (state.tab === "brief" && $("#blist")) $("#blist").innerHTML = briefList();
});

document.addEventListener("submit", async (e) => {
  if (e.target.dataset.act !== "ask") return;
  e.preventDefault();
  const q = new FormData(e.target).get("q").trim();
  if (!q) return;
  await runAsk(q); render(false);
});

(async function init() {
  const data = await getJSON("data/snapshot.json");
  if (!data) { $("#view").innerHTML = `<div class="empty"><b>No data yet.</b>Run <code>python3 -m finn.snapshot</code> and reload.</div>`; return; }
  state.data = data;
  state.enrich = (await getJSON("data/enrich.json")) || {};
  state.research.index = (await getJSON("data/research/index.json")) || {};
  state.ledger = (await getJSON("data/ledger.json")) || {};
  header(); render(false);
})();
