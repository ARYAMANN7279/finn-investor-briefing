# FINN build workflow: edited prompt reconstruction

This is a structured rewrite of the goals and review steps recorded in [AI-BUILD-HISTORY.md](AI-BUILD-HISTORY.md). It was assembled after the build; these are **not verbatim prompts** and should not be read as messages that were sent at the time. The original conversation remains below the reconstruction in the history file. Stage references point to the recorded turns and project artifacts that support each part.

The sequence shows how the work moved from the ENAM brief to a checked, published prototype. Each prompt keeps a clear scope, constraints, output, and review gate so a future session can continue the project without treating one broad request as approval for every decision.

## 1. Turn the challenge brief into a build plan

**Recorded basis:** History, Turn 1; `PLAN.md`.

```text
I am building FINN for the ENAM Holdings AI Engineer challenge. Read the supplied brief and reference material first, then plan the smallest complete investor workflow that meets the brief.

Before coding:
- List the explicit requirements and map each one to a screen, data source, or submission artifact.
- Separate brief requirements from your design assumptions.
- Propose a mobile-first flow for a filing brief, company research questions, and watch rules.
- Identify source, freshness, model-quota, and hosting constraints.

Use annual reports and earnings-call transcripts as the research evidence; use filing documents for the push-side brief and results extraction. Be clear where the prototype must rely on a dated snapshot. Do not invent coverage or work around blocked sources.

Deliver a short scope, architecture, data plan, risks, and acceptance checks. Flag decisions that need my answer, then wait for review before expanding the scope.
```

## 2. Inspect sources and choose a defensible data path

**Recorded basis:** History, Turn 1; cached fetcher, Screener parser, Yahoo end-of-day prices, and dated snapshot in `finn/` and `docs/data/`.

```text
Inspect the existing project and the public sources needed for FINN before building the data pipeline. Check what the sources actually return and document any access limits.

For this prototype:
- Use Screener for company, quarterly, and recent-filing data; Yahoo Finance for end-of-day prices; and annual reports plus earnings-call transcripts for company research.
- Keep source URLs and retrieval dates with the data.
- Cache requests and respect rate limits. If an exchange blocks automated access, record the limitation and use an honest dated snapshot; do not evade its checks.
- Validate ticker coverage, dates, units, and missing values before publishing a snapshot.

Deliver a source map and a reproducible data plan first. After it is reviewed, implement the fetchers and parser in the existing architecture. The app must show when data is dated or unavailable.
```

## 3. Build the investor flow around the challenge use case

**Recorded basis:** History, Turn 1; `docs/` app, `docs/logic.js`, and browser-logic tests.

```text
Implement FINN as a responsive, static web app using the existing project structure. Keep the main workflow to three views:

1. Brief: rank and filter company announcements, with routine filings still available.
2. Ask: answer a company question from the prepared, cited research sheets.
3. Watch: let me adjust alert thresholds and category preferences, and show model usage.

Keep ranking, alert evaluation, and financial arithmetic in deterministic JavaScript. Make controls usable on a phone, preserve clear empty and partial-data states, and label the snapshot date. Do not imply that the app streams live exchange data.

Before calling this stage done, check the key interactions at a phone-sized viewport and add focused tests for the pure ranking and alert logic. Report any view that could not be checked.
```

## 4. Add the model layer within the available quota

**Recorded basis:** History, Turns 2–4 and 6–8; explicit approval in Turn 4 to use Flash models, fallback, and research sheets; `finn/llm.py`.

```text
The Gemini key is configured locally. Build the FINN model layer using the available Flash models, a documented fallback chain, and cached requests. Never print or commit the key.

Keep model work narrow and structured:
- Read results figures from the filing and compare them with Screener values in code.
- Summarize management changes and material filings from the supplied filing text only.
- Extract research facts and forward-looking statements from the supplied annual reports and calls, with a short quote and page for every item.
- Judge promises only against the results data passed into that step; calculate growth, margins, and trailing totals in code.

Return schema-constrained JSON, handle quota and source failures plainly, and record which model produced each sheet. Do not present a result as verified when required comparison values are missing. Start with representative companies, inspect their outputs, then continue across the four selected research names.
```

## 5. Review the evidence and correct observed failure modes

**Recorded basis:** History, Turn 4 and Turn 12; corrections described in `PROMPT-FLOW.md`, `finn/research.py`, and the refreshed research sheets.

```text
Review the generated FINN results cards and research sheets against their source documents. Treat model output as a draft until the source and code checks pass.

Check specifically that:
- A displayed quote appears on the page cited, and its source document is linked.
- A concall analyst question is not presented as management guidance.
- Repeated transcript promises are not counted as separate promises.
- Duplicate copies of the same transcript do not add evidence twice.
- Figures used in a verdict match the computed comparison table; the model does not do financial arithmetic.
- Missing or untestable evidence remains explicitly unknown or not measurable.

Fix demonstrated errors, regenerate affected sheets when needed, and report what changed along with the remaining limits. Keep source-backed facts separate from interpretation.
```

## 6. Finish the release and submission artifacts

**Recorded basis:** History, Turns 12–13; public-repo approval in Turn 13; `README.md`, `docs/`, and the completion summary in `AI-BUILD-HISTORY.md`.

```text
Prepare the verified FINN project for review and publication. First check the repository state, README run steps, public files, generated research sheets, and configured Pages paths.

Release checks:
- Confirm secrets and private submission details are excluded from tracked files.
- Confirm the README explains the architecture, dated data, model routing, coverage, and known limitations.
- Run the existing Python and browser-logic checks and report exact results.
- Check that the Pages app paths and service-worker cache match the published layout.
- Keep the cover email as a local draft for me to review and send.

Summarize the release plan and URLs before publishing. After I approve the public repository and hosting plan, publish the reviewed branch and verify the deployed app loads. Do not send the submission email for me.
```

## What this reconstruction does and does not claim

The structure above is editorial: it organizes the real work into reviewable stages and turns the recorded goals into usable prompts. It does not claim that these exact words were typed, that every proposed gate happened at the time, or that the prototype meets requirements beyond the checks recorded in the history and repository. The stage references and [PROMPT-FLOW.md](PROMPT-FLOW.md) provide the implementation details; the original messages provide the verbatim record.
