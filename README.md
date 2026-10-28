# FINN: a briefing that talks back

Built for the ENAM Holdings AI Engineer Build Challenge (Financial Investment Agent). A mobile-first web app for an Indian equity investor.

**Live prototype:** [FINN on GitHub Pages](https://aryamann7279.github.io/finn-investor-briefing/) · **Source:** [GitHub repository](https://github.com/ARYAMANN7279/finn-investor-briefing)

- **Brief (push).** Pick a window (24 h, 3 days, 7 days, or a custom window up to 10 days). FINN ranks what the portfolio's companies filed, folds related filings into one card, hides routine paperwork behind a single line, and flags unusual volume or price moves. Results cards show Revenue, operating profit (EBITDA proxy), PBT and PAT against last quarter and last year using Screener's quarterly table. A separate badge reports whether Revenue, PBT and PAT extracted from the filing PDF all match Screener within 1.5%, partially match, or differ. Management changes show who comes and goes, from when, why, and a profile only when the filing itself contains one.
- **Ask (pull).** Type a ticker or a question ("did Asian Paints deliver on its guidance?"). The answer is a research sheet built only from the company's annual report and concall transcripts. The hero view is **Promised vs Delivered**: what management committed to on earlier calls, tested against eligible results periods (quarter-end month at or after the call month). Every displayed claim carries a quote matched against its cited page (case and punctuation normalized), the document, and the page.
- **Watch.** Alert rules as sliders (volume multiple, price move, materiality bar) and category toggles, plus a token and cache meter.

## Run it

```bash
python3 -m http.server 8765 --directory docs     # open http://localhost:8765 on a laptop or a phone on the same network
```

The app is static: it reads `docs/data/*.json` that the Python side prepares. Ranking, windows, thresholds and the results maths run in the browser (`docs/logic.js`), so the sliders respond instantly and hosting needs no server.

Rebuild the data (needs Python 3.10+ and `pip install pymupdf`; the model steps need `GEMINI_API_KEY` in a git-ignored `.env`):

```bash
python3 -m finn.snapshot               # filings, prices, quarterly tables, document links for 22 companies
python3 -m finn.enrich                 # results numbers, management changes, one-line summaries
python3 -m finn.research TICKER ...    # research sheet; works for any NSE ticker Screener covers
```

Tests: `python3 -m unittest discover -s tests` and `node --test tests/logic.test.mjs`.

## Build notes

- [AI-BUILD-HISTORY.md](AI-BUILD-HISTORY.md) is the historical session log, with sensitive details redacted.
- [WORKFLOW-PROMPTS.md](WORKFLOW-PROMPTS.md) is a polished, reusable prompt sequence for building and reviewing FINN. It was written after the build and is not presented as historical dialogue.
- [PROMPT-FLOW.md](PROMPT-FLOW.md) explains the prompts FINN sends to its models and how the build stages fit together.

## How it is put together

| Piece | What it does | Where the model is used |
| --- | --- | --- |
| `finn/sources/` | Yahoo chart endpoint for end-of-day price and volume; Screener company pages for recent filings, the quarterly results table, annual-report and transcript links | none |
| `finn/classify.py` | 17 filing categories, subtype and a base materiality score from the title | only titles the rules cannot place are flagged ambiguous |
| `finn/extract.py` | Revenue, PBT and PAT from the filing PDF; units converted in code; all three are compared with Screener's quarterly table at 1.5% tolerance | small model reads the table; the UI's EBITDA proxy comes from Screener operating profit |
| `finn/enrich.py` | management-change summaries and one-line summaries of other material filings | small model, filing text only |
| `finn/research.py` | PDF → page-tagged chunks → claims and facts with quotes → quotes checked against their cited page → older promises judged against later quarters → business, narrative, bull and bear view citing item ids → ids become footnotes | small model extracts; stronger model judges and writes |
| `finn/llm.py` | Gemini client, fallback chains, JSON schemas, request-level disk cache, token ledger | |
| `docs/` | vanilla ES modules, no build step, installable PWA | none |

### Efficiency
- **Routing.** Extraction, which is most of the tokens, runs on Gemini 3.5 Flash-Lite. A stronger tier is used only for the promised-versus-delivered judgement and the written view.
- **Caching.** Every model request is cached by its exact content, so a document is paid for once. PDFs and web pages are cached on disk too.
- **Chunking and pruning.** Annual reports (about 300 pages) are cut to the pages that talk about outlook, risk, strategy and borrowings before any model sees them. Transcripts are chunked on paragraph boundaries with overlap. Results filings send only the pages that look like the results table.
- **Arithmetic stays in code.** Growth rates, trailing-year sums, unit conversion and the Screener cross-check are computed by code, not the model.

### Honesty rules the code enforces
- A claim whose quote is not found on its cited PDF page is dropped. Matching ignores case and punctuation to accommodate PDF text extraction.
- Statements by analysts in transcripts are not counted as company claims.
- Management-change profiles come only from the filing text. FINN does not look people up elsewhere.
- Every model-written piece in the app names the model that wrote it.

## What is live and what is a snapshot
- Prices and filings are a dated snapshot (`docs/data/snapshot.json`, stamped in the header). The exchange APIs from NSE and BSE refuse scripts and I did not work around that. Screener lists each company's five most recent filings, so a 7-day digest is real but thin for busy companies.
- Research sheets are prepared for Asian Paints, Avenue Supermarts (D-Mart), Persistent Systems and Cipla. The engine builds one for any NSE ticker from the command line; the hosted app serves prepared sheets only.
- Concall source labels have month-level precision. The promise comparison treats quarter-end months at or after the call month as eligible; exact historical results-release dates are not available for every quarter.
- At the 28 Oct refresh, the fallback chain used Gemini 3.5 Flash-Lite for both extraction and the stronger comparison/writing steps. Each sheet records its model; this is not a Pro-grade second opinion.

## What I left out
- Live exchange feed and push notifications (needs a server and a feed the exchanges allow scripts to use).
- Scanned results filings with no text layer are skipped rather than guessed at.
- Items from the reference brief that the research sheet does not cover as separate sections: guidance is folded into Promised vs Delivered, and cash quality sits inside Balance sheet and cash.

## Where next
A small server that polls the exchange feeds the exchanges permit and sends web-push alerts; a Pro-grade second opinion on verdicts; and an eval set of hand-checked promises so verdict quality can be measured instead of eyeballed.
