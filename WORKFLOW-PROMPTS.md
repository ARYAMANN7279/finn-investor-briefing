# Structured AI build prompts for FINN

These prompts are a clean, reusable workflow for building or continuing FINN. They were written after the build; they are not quotes from the historical conversation. For the actual session record, see [AI-BUILD-HISTORY.md](AI-BUILD-HISTORY.md).

Use them in order. Replace bracketed inputs with the challenge brief, repository, or decision for that stage. Keep each stage reviewable before moving on.

## 0. Understand the challenge

```text
You are helping me build FINN for the ENAM Holdings AI Engineer Build Challenge.

Goal
Read the supplied challenge brief and reference material, then turn them into a testable product plan.

Inputs
- Challenge brief: [path or attachment]
- Reference material: [path or attachment]
- Deadline and submission format: [details]

Constraints
- Treat the supplied brief as the source of truth. Separate explicit requirements from your assumptions.
- Prioritize a small, working investor product over features that cannot be verified.
- The pull side must use company annual reports and earnings-call transcripts only.
- Do not bypass access controls or invent live data, evidence, or results.
- Do not write code yet.

Deliver
1. A requirement-to-feature table with a measurable acceptance check for every requirement.
2. A short product point of view and a prioritized scope: must ship, could ship, out of scope.
3. A data and model plan, including source freshness, failure behavior, and cost controls.
4. The top risks and the decisions that need my input.

Done when every requirement maps to an acceptance check and every unresolved assumption is visible.
Stop for my review before implementation.
```

## 1. Inspect the existing repository

```text
Continue FINN in the existing repository; do not replace it with a new scaffold.

Goal
Understand the current implementation and identify the smallest changes that satisfy the approved plan.

Inputs
- Repository: [path]
- Approved plan: [path]
- Current user request: [request]

Before editing
- Read the README and all applicable AGENTS.md instructions.
- Check git status, recent commits, tracked and untracked files, and ignored secrets.
- Trace each relevant feature from data source to stored data to UI.
- List existing tests and known limitations.

Constraints
- Preserve user changes and the working architecture unless evidence shows a defect.
- Never print, commit, or copy credentials. Do not change remotes or publish without explicit authorization.
- Separate confirmed bugs from optional polish.

Deliver
1. A concise architecture map.
2. A bug and gap list ranked by user impact, with file references and evidence.
3. A small implementation plan with acceptance checks.

Do not start unrelated work. Report the findings before broad refactors.
```

## 2. Build the data pipeline

```text
Implement the approved FINN data pipeline for portfolio filings, quarterly results, and end-of-day prices.

Goal
Produce a dated, auditable snapshot that the browser app can consume without a server.

Inputs
- Approved data design: [path]
- Portfolio and research tickers: [list]
- Existing fetchers and fixtures: [paths]

Constraints
- Use the named public sources and document what each source supplies.
- Respect rate limits and access controls. Do not evade bot checks, logins, or blocks.
- Cache fetched data and retain stale data when a refresh fails, while showing its timestamp.
- Keep parsing deterministic where possible. Do not use a model for arithmetic or source discovery.
- Validate dates, units, missing values, and ticker coverage before writing the snapshot.

Done when
- Each supported ticker either has a valid, timestamped record or a clear recorded failure.
- Filing categories and result rows match the source fixtures.
- A rebuild is repeatable and does not expose credentials.
- The app labels stale or unavailable data honestly.

Report the sources, snapshot timestamp, failures, and checks performed.
```

## 3. Build the mobile investor workflow

```text
Implement the approved FINN experience in the existing mobile-first app.

Goal
Help an investor see what changed, ask a grounded company question, and adjust alert rules.

Required views
- Brief: rank filings in a selectable window, group related notices, and keep routine filings accessible.
- Ask: route a company question to a prepared, sourced research sheet.
- Watch: adjust alert thresholds and category preferences; show the data and model freshness.

Constraints
- Reuse the existing framework and data format unless a concrete defect requires a change.
- Keep ranking, alert math, and financial calculations deterministic and testable.
- Make links, dates, units, empty states, and partial results clear on a phone-sized screen.
- Escape user-visible text and preserve keyboard and screen-reader access.
- Never imply that a dated snapshot is live.

Done when
- The three views work at a 375 px viewport and with missing optional data.
- Controls update their results immediately and can be reset or persisted as designed.
- Every numeric result has a defined source and unit.

Show the changed screens and list the acceptance checks completed.
```

## 4. Add the evidence-grounded model workflow

```text
Implement the FINN model stages as small, structured transformations.

Goal
Extract useful filing and research facts while making unsupported claims easy to reject.

Inputs
- Source documents: [specific filing, annual report, or transcript]
- Output schema and downstream consumer: [paths]
- Model and quota constraints: [details]

Prompt structure for every stage
1. Role and one-sentence task.
2. Allowed evidence and explicit exclusions.
3. Field-by-field output definitions and valid enums.
4. Rules for missing, conflicting, or untestable evidence.
5. A small output schema; no prose outside the schema.

Constraints
- Only use evidence supplied to that stage. Keep model arithmetic out of the pipeline.
- Copy supporting quotes from the source; validate the words and cited page in code.
- Separate management statements from analyst questions.
- Compare promises only with results reported after the promise and within the available data.
- Treat a schema-valid answer as untrusted until semantic and source checks pass.
- Cache by the full request, record the model used, and fail clearly when quota or source data is unavailable.

Done when
- Valid outputs pass schema and source checks; invalid quotes, pages, figures, or IDs are dropped or flagged.
- Empty evidence produces an explicit unknown state instead of a guess.
- A reviewer can open every displayed citation and find the cited words.
```

## 5. Review and verify

```text
Review FINN against the approved acceptance checks. Fix demonstrated defects in scope.

Goal
Find incorrect claims, broken interactions, stale-data confusion, and regressions before release.

Inputs
- Approved plan and acceptance checks: [paths]
- Changed files: [git diff]
- Current snapshot and prepared research sheets: [paths]

Review sequence
1. Check source-to-UI data flow and labels for units, dates, and freshness.
2. Check financial comparisons, quote-to-page matching, and evidence references.
3. Check empty, partial, stale, and error states.
4. Run the existing test commands and add focused tests for fixes.
5. Run a local production-like server check; inspect a 375 px layout if a browser is available.

Constraints
- Report exactly what ran and what could not be checked.
- Do not turn a warning or limitation into a claim of success.
- Do not expand scope to unrelated refactors.

Done when every acceptance check has a result and remaining risks are stated plainly.
```

## 6. Prepare the submission

```text
Prepare FINN for the challenge submission using the verified implementation.

Goal
Make the repository, hosted app, AI build history, and covering note easy for an evaluator to review.

Inputs
- Verified branch and commit: [details]
- Hosting and repository URLs: [links]
- Required email format and deadline: [details]

Deliver
- A README with run steps, feature map, data freshness, model routing, tested names, and limitations.
- A concise architecture and prompt-flow explanation.
- The historical AI build log, plus a clearly labeled structured prompt workflow for future runs.
- A covering-email draft with placeholders for any missing links or user-only details.

Constraints
- Never include keys, tokens, private local paths, or personal identifiers that are not required for submission.
- Distinguish historical facts from polished prompts written after the build.
- Do not send email, create a public repo, or push commits unless I explicitly authorize that action.
- Do not describe an untested feature as complete.

Done when a reviewer can run the app, inspect its evidence, understand its limitations, and find every required artifact.
```

## Compact prompt template

For a new task, keep this structure and fill in the specifics:

```text
Goal: [one observable outcome]
Context: [challenge requirement and current implementation]
Inputs: [files, data, links]
Constraints: [source, privacy, cost, architecture, scope]
Plan: [small ordered steps; inspect before editing]
Acceptance checks: [observable evidence that defines done]
Review: [what to summarize, risks, and remaining gaps]
```
