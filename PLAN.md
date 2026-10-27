# FINN build plan (ENAM Holdings AI Engineer Build Challenge)

Deadline: **Sun Nov 1 2026, 11:59 PM** (the notice says so; email assessment@enam.com, subject "ENAM - IIT screening - 2027"). Released Oct 27.
Submit: deployed mobile link or responsive web, GitHub repo, AI build history (export/share links), covering-email writeup. Aryamann sends the email himself.

## Rules from the brief that shape every decision
- Grade: creativity, product sense, judgment, architecture. NOT completeness. "Thin-but-working beats broad-but-broken. A demo that doesn't run is the worst outcome."
- Pull side must be grounded in **primary sources only** (annual reports + concall transcripts). No news, broker notes, or model outside knowledge.
- Push side: windowed digest (default 24 h, user-chosen window), triggered alerts with configurable thresholds (announcement types; volume > ~2x average; price move beyond +/-X%). Management change -> background on the incoming person. Quarterly results -> Revenue, EBITDA, PBT, PAT, QoQ and YoY.
- Portfolio 15 to 20 NSE/BSE names; 3 to 5 extra names for research; engine must work on **any NSE ticker** where data exists.
- Efficiency earns bonus points: model routing, caching, chunking. No model restrictions. Free tiers are enough.

## Product point of view
An investor should not open a list. FINN is a **briefing that talks back**, three tabs on a phone:
1. **Brief (push)**: one ranked stack for a chosen window. Each card has a materiality score and a one-line "why you care". Routine filings are collapsed into "N routine hidden" (one tap to peek). Results and management-change cards expand into the rich views the brief asks for.
2. **Ask (pull)**: a command bar. Type a ticker or a question; FINN answers with a research sheet. Hero view = **Promised vs Delivered** (management guidance and growth claims from transcripts against what the following quarters actually reported), every claim carrying a quote and a page/transcript reference so it can be checked.
3. **Watch**: alert rules written as sentences with sliders ("volume above 2.0x its 20-day average", "move beyond 4%", "tell me about results and management changes"), plus a live cost meter showing what the model spend was.

## Architecture (small on purpose)
- `finn/sources`: Yahoo chart endpoint for end-of-day price and volume; Screener company pages (robots.txt allows them) for recent filings, results table, annual-report and transcript links; BSE-hosted PDFs by link.
- Filings snapshot: NSE/BSE APIs block scripts and I do not work around bot protection. Recent filings come from the Screener page; a dated snapshot file can be added by reading the exchange pages in a normal browser.
- `finn/classify`: rules first (free), LLM only for the ambiguous remainder. Categories from the reference doc (17 of them).
- `finn/extract`: results PDF -> headline numbers with a cheap model, cross-checked against Screener's quarterly table where possible. EBITDA is not reported on filings; defined as PBT + finance cost + depreciation - other income, stated in the UI.
- `finn/research`: PDF -> text (PyMuPDF) -> chunks -> cheap model extracts guidance/claims -> strong model only for the promised-vs-delivered comparison. Cache by document hash so each document is paid for once.
- `app/`: single static mobile-first web app (installable PWA) reading pre-built JSON, plus an optional local server for live research on any ticker.
- LLM: Gemini free tier (Flash for bulk, Pro only for the comparison). Key is Aryamann's, in a git-ignored `.env`.

## Honesty rules for the writeup
Say what is live and what is a snapshot. Say what was tested on which tickers. Never present a number the code did not extract from a document.

## Schedule
- Oct 27: data layer (prices, screener scraper), portfolio picks, repo skeleton.
- Oct 28: classification, alerts engine, results extraction.
- Oct 29: research engine on 3 to 5 names (needs his Gemini key).
- Oct 30: mobile app, interaction polish.
- Oct 31: phone-viewport testing, deploy, README, covering note, AI-history export. Nov 1: buffer; he reads everything and sends the email.
