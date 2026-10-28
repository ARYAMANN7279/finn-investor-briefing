# FINN prompt flow and build workflow

This page describes the prompts FINN sends to its models and the decisions behind the build. The prompt text lives in `finn/extract.py`, `finn/enrich.py`, and `finn/research.py`. The historical conversation is in [AI-BUILD-HISTORY.md](AI-BUILD-HISTORY.md); polished prompts for a repeatable build are in [WORKFLOW-PROMPTS.md](WORKFLOW-PROMPTS.md).

## 1. The model pipeline

Every call goes through `finn/llm.py`: a tier (`bulk` or `strong`), a JSON schema for the answer, a fallback chain of Gemini models, a cache keyed by the exact request, and a token ledger. Each stage supplies a structured response schema. Source boundaries are enforced in the stage prompt and validating code; they are not expressed with identical wording in every prompt.

| Stage | Tier | Input | Output (schema) | What code does with it |
| --- | --- | --- | --- | --- |
| 1. Results table (`extract.py`) | bulk | up to 5 PDF pages that look like the results table | current, previous-quarter, and year-ago revenue, PBT and PAT; unit; optional bank interest fields | converts units to crore; compares current revenue, PBT, and PAT with Screener; says verified only when all 3 compare within 1.5% |
| 2. Management changes (`enrich.py`) | bulk | first 14,000 characters of the filing | summary; people with action (enum), role, effective date, reason, bio | bio is kept only if the filing contains one; the app never looks people up elsewhere |
| 3. One-line summary (`enrich.py`) | bulk | first 8,000 characters of a material filing | one sentence, at most 28 words | shown as the card's lead line |
| 4. Evidence extraction (`research.py`) | bulk | one page-tagged chunk (about 22,000 characters) of an annual report or concall | `claims` (forward-looking, with speaker enum, topic enum, target, horizon) and `facts`, each with a quote and page | **drops any item whose quote does not match its cited page**; drops analysts and any concall quote containing "?"; removes duplicates from overlapping chunks |
| 5. Promised vs delivered (`research.py`) | strong | older promises plus a quarterly table with growth, trailing-four-quarter revenue, operating profit, margin and net-profit values computed in code; eligible periods start with the call month | verdict enum (delivered, partly, missed, too_early, not_measurable), evidence sentence, quarters used, `same_as` for repeated promises | checks that financial values of 100 or more in the evidence appear as values in the table (`numbers_ok`; calendar years are ignored); folds repeats together |
| 6. Research view (`research.py`) | strong | the verified items as `id | source | statement` | business, narrative, bull, bear and balance text, citing item ids only | turns ids into numbered footnotes with quote, document and page |

The tier is a routing preference, not a promise about which model answers. All four sheets rebuilt on 28 Oct record Gemini 3.5 Flash-Lite for extraction and writing; the stronger tier fell through its fallback chain. The chosen model is stored in each sheet.

The transcript source provides call labels only to the month. `quarters_after()` therefore treats table periods ending in the call month or later as eligible; it cannot check the exact results-release date for each historical quarter. The UI states this timing approximation.

### Prompt and evidence rules
- Research extraction and writing explicitly say to use only the supplied text and never use outside knowledge. Filing enrichment is limited to the filing text. The results-table prompt names the fields and table pages to read.
- Research quotes are limited to 40 words and matched against the page they cite. Matching ignores case and punctuation to account for PDF text extraction, while preserving the quoted words.
- Arithmetic is never asked of the model: growth and trailing sums are computed in code and supplied as inputs ("use them rather than calculating").
- Each stage can answer "I can't tell": `not_measurable`, `too_early`, `unclear`, empty lists, or a section that says the list cannot support it.

### Prompt problems found and fixed
| Problem seen in output | Fix |
| --- | --- |
| An analyst's question was quoted as a management promise | `speaker` enum in the schema, a rule that only management counts, then a plain-code rule dropping concall quotes with "?" |
| The same margin guidance counted four times | `same_as` in the judge schema; repeats are merged and shown as "repeated n times" |
| Raw ids like "(0.37)" in the written text | ids returned in separate arrays; code makes the footnotes |
| The same transcript filed twice counted as two calls | code skips a transcript whose text matches an earlier one |
| A quote could be present on a different page than the cited page | code checks each quote against its cited page |
| A number in model evidence could match only part of a larger table value | code compares numeric values rather than substrings |
| Model overloaded or out of free quota | retry rounds with backoff and a fallback chain; every sheet records the model that wrote it |

The cross-check does not call a partial comparison "verified": all three filing figures must be available and agree. A real zero is treated as a value, not as missing data.

## 2. Build workflow (retrospective)

| Stage | What I decided | What Claude Code did |
| --- | --- | --- |
| 0. Brief | Read the brief and reference. Chose to do the research side first-class and keep scope to a working phone prototype. | Read both PDFs; wrote `PLAN.md`: three tabs, primary sources only, honesty rules |
| 1. Data | Accepted a dated snapshot because NSE and BSE refuse scripts. No bot-check workarounds. | Built the cached fetcher, Screener parser, Yahoo prices, filing classifier |
| 2. App | Mobile first; ranking runs in the browser so sliders are instant | Wrote the vanilla JS app and the pure logic module with tests |
| 3. LLM layer | Free tier only; cheap model for bulk, stronger only where judgement is needed | Gemini client with fallback, cache, ledger |
| 4. Research | Every claim needs a checkable quote; arithmetic in code | Chunking, extraction, quote verification, judge, view |
| 5. Review | Read the first sheets myself and sent back what looked wrong | Fixed the analyst, repeat and footnote problems above |
| 6. Publish | Approved a public repo and Pages after seeing the exact plan; rotated a key that had been pasted | Created the repo, moved the app to `docs/`, served it on Pages |

The historical messages are shorter and looser than a production prompt. [WORKFLOW-PROMPTS.md](WORKFLOW-PROMPTS.md) provides structured, copy-ready prompts for challenge analysis, repository inspection, data, UI, model stages, verification, and submission preparation. They are clearly labeled as prompts written after the build; the historical log remains a record of what was actually said.
