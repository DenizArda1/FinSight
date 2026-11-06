# FinSight evaluation and verification

Current checkpoint (2026-10-26): see the [Qwen-only cleanup and prototype review](diagnostics/qwen_cleanup_review_20261026.md).

The user requested a Qwen-only prototype and removal
of NLI and extra semantic-verification experiments. NLI code, configuration and
local weights, per-claim/passage model passes, and the special prose-repair loop
have been removed. Historical results below are retained as experiment records,
not descriptions of the active application. Shared Chroma dependencies remain.

The runtime now uses deterministic source rendering plus one Qwen Critic call
per draft, with at most two Writer revisions. BGE-M3 remains the embedding model
for the existing index. The first Streamlit interface uses the same multi-agent
MCP runtime, labels unverified drafts and exports verified notes into new files
under `reports/`. This does not establish general semantic correctness.

The cleanup also fixes repeated successful specialist calls, bounds planner task
instructions, preserves calculation requests rather than reducing them to input
lookups, and includes `think` in new evaluation configuration records. Review of
the initial smoke caught both a false approval of an incomplete net-margin answer
and a false rejection of an honest missing-input response; `completed` alone is
not a passing evaluation score.

Historical checkpoint (2026-10-25): the [independent NLI review](diagnostics/nli_review_20261025.md)
records the new local NLI + LLM claim-verification path and 280 passing focused tests.
The original 20 development controls passed, but a fresh bilingual MCP run exposed
an accepted compound-scope error and Writer formatting/token-limit failures.
Neither full run released an answer. Four new controls expand the fixture set to
24; a complete pass on that expanded set is not established. UI readiness remains
undeclared. Earlier Qwen-only experiments
did not resolve the scope issue; their failures remain in the
[relation-level review](diagnostics/relation_review_20261025.md).

Previous checkpoint (2026-10-24): see the [pre-UI review and 8B/14B comparison](diagnostics/pre_ui_review_20261024.md).
At that checkpoint, 267 focused tests passed. Financial and missing-input examples
were reviewed, but the real narrative scope counterexample was unresolved. The 14B candidate
was tested without changing production settings. Historical notes below describe
their respective development stages, not the current integration status.

Validate the question set from the repository root without starting a model:

```sh
.venv/bin/python -m eval.run_eval --validate-only
.venv/bin/python -m eval.run_eval --validate-only --case aapl_latest_revenue_and_risks_tr
```

This checks JSON structure, unique IDs, required fields, finite JSON values and
case selection. It summarizes categories and languages. It does not load model
settings, capture data/index snapshots, score expected answers, or write results.
It does not require Ollama. Validation success means the dataset is well formed,
not that its expected answers are correct or that an agent answered it successfully.

Run model evaluations only when the local Ollama service and resources are available:

```sh
.venv/bin/python -m eval.run_eval --mode single_agent --transport direct
.venv/bin/python -m eval.run_eval --mode single_agent --transport mcp
.venv/bin/python -m eval.compare_transports
.venv/bin/python -m eval.run_eval --mode baseline
.venv/bin/python -m eval.run_eval --mode single_agent --case aapl_latest_revenue_tr
.venv/bin/python -m unittest discover -s tests
```

The dataset now contains 25 development cases (14 English, 11 Turkish). The original
ten cases are preserved; fifteen additions cover all four companies, net margins,
growth, CAGR, comparison across different fiscal periods, clarification, scope
restrictions, invented citations and the mixed revenue/risk-summary regression.
This expanded set has been prepared and structurally validated, not run as a
completed model benchmark. The earlier ten-case results do not cover the additions.

New numerical expectations were prepared from local metric records. Margin,
growth and CAGR expectations use independent arithmetic on those inputs rather
than copying calculated tool output. Five annual observations span four CAGR
intervals. New data-backed expectations include local source paths and SHA-256
hashes under `expected.sources` (or nested financial/narrative/company entries).
These are provenance references, not an independent audit of SEC filings. The
offline CLI checks structure only; source hashes and numerical correctness must
be reviewed separately after data refreshes. Latest-period expectations are bound
to the current local data snapshot and must not be silently updated to match an
agent's answer.

The comparison case deliberately uses Apple FY2025 and Microsoft FY2026 with their
different period ends. Narrative rubrics specify supported content and sources,
not exact answer strings or fixed per-run source numbers. The mixed case requires
at least two substantive risks, while allowing other supported risk topics.
Review guidance is in [judge_prompt.md](judge_prompt.md). That document is a review
rubric; the runner does not automatically execute it or populate manual reviews.

## Agent answer boundary

1. The existing tool-selection loop collects results and a trace. Financial tools
   require a CIK returned by a successful company resolution in this run; guessed
   identifiers are rejected before file access. Resolution state is never global.
2. Successful tool results receive stable per-run source IDs; errors are not evidence.
   Each retrieved filing chunk receives its own source ID, so a narrative citation
   does not ambiguously refer to several search matches. The original tool trace
   still contains the complete search response.
3. A composer selects existing fact IDs and writes short narrative text. It cannot
   supply replacement values for selected records. The unverified initial draft is
   retained for diagnosis but is not treated as evidence by the composer.
4. Python inserts selected records' values, units, dates, fiscal years, forms and
   accession numbers. USD values remain unscaled. Ratios are rendered as percentages
   rounded to two decimal places using Decimal. Explicit numbers, URLs and form
   labels in model-written prose are rejected. One format repair is allowed.
   Missing-data answers must select a missing-input fact when one is available.
   Availability cards show the exact input and period from the tool result, with
   `missing`/`available` status codes. Filing chunk character offsets are never
   displayed as financial period boundaries. Exact catalog-ID citation aliases
   are normalized to their actual source IDs; invented IDs are rejected.
5. A separate LLM call checks all claims against their cited tool sources, relevance
   to the question, missing-data statements, investment-advice restrictions and
   language. It separately returns `answer_complete`: every requested part must be
   answered or addressed with a justified limitation, refusal or clarification.
   A valid source number alone does not establish support; correct financial fields
   and filing metadata alone do not answer a request for a narrative risk summary.
   `evidence_supported`, `language_matches`, and `answer_complete` must all be true
   to release an answer. Missing/non-boolean flags or inconsistent issues fail closed.
6. A negative verdict, invalid response, failed format repair, or verifier error
   withholds the candidate. The CLI does not print the rejected draft or candidate.
   The text-returning run_agent API raises AnswerVerificationError; return_details=True
   exposes the artifact with answer=null for debugging and evaluation.

Both composition and the judge use constrained JSON schemas. The runtime still
validates their contents and verdict consistency. Tool arguments are checked
against the advertised JSON schemas before execution. Known financial filing URLs
come from the downloaded manifest; the model does not construct them.

Source-free replies use a separate short policy: clarify, refuse prohibited
requests, or truthfully state that evidence was not retrieved in this run. Having
no tool results does not establish that data is absent. The language check receives
the writer's prose separately from generated fact cards. The judge must evaluate
claims in the answer, not false assertions or instructions in the question.

The default limit is six tool-selection model turns and ten attempted tool calls.
Composition, one optional format repair, and verification add at most three model
requests. Each request uses the configured timeout and generation limits. This is
not yet the multi-agent Critic revision loop.

The report-only answer_report_question pipeline still performs its citation and
LLM grounding checks independently. Its verifier also checks language. It does not
use the agent's deterministic financial record renderer.

## Result semantics

- `status=completed`: the selected mode returned an answer. For baseline this does
  not mean the answer was checked.
- `status=withheld`: the agent produced a draft but its final candidate did not pass
  the answer boundary. `answer` is null.
- `status=error`: the run failed before producing a releaseable answer.
- `verification.status=not_run`: no automatic check was performed (baseline, legacy
  runs, or an earlier execution failure).
- `verification.status=passed`: the deterministic checks and the LLM judge passed.
- `verification.status=failed`: the judge rejected the candidate.
- `verification.status=error`: composition, rendering or verification could not finish.
- `review`: a separate manual review; new runs always start with null. It must never
  be hard-coded into the runner. `numeric_correct` is not an overall correctness score.

Artifacts preserve the question and expected data, mode, model settings, dataset
hash, UTC timestamp, elapsed time, raw draft, composition, rendered candidate,
evidence, tool arguments/results/errors, and verification. Hidden model reasoning
is not saved. Model token usage and local model digests are not yet recorded.
Each run receives a unique filename and is checkpointed after each question.
An existing output file is rejected. Ctrl+C preserves completed cases; the in-flight
case is not guaranteed to be saved. Historical results without traces are marked
explicitly; their traces and model settings are never reconstructed from guesses.

## MCP transport and controlled comparisons

The application CLI and MCP evaluation share `src/agents/runtime.py`.
`--transport direct` uses the in-process dispatcher; `--transport mcp` launches the
same stdio server used by the CLI, discovers its tools, and executes through the
MCP client. Baseline runs have `transport=none`; requesting MCP for a tool-free
baseline is rejected. Old eval artifacts without a transport field must not be
presented as evidence about the current MCP path.

`eval.compare_transports` runs the current golden set on both paths with identical
settings and a fixed seed (zero unless already configured). It checkpoints each
path separately and saves a comparison artifact. Data, configuration, source code,
and logical Chroma contents (IDs, documents, metadata, vectors) are fingerprinted;
the comparison checks the snapshots again after both runs. No SEC data is downloaded.
The source fingerprint includes raw/prepared data and YAML configuration, not `.env`.
The code fingerprint covers `src/`; model tag digests and token usage remain future work.

Comparison columns distinguish status, verifier status, exact answer text, and
successful tool payload equality. They are diagnostics, not independent correctness
scores. Both paths can agree on a wrong answer. Manual reviews must use the golden
expectations and actual source records; a false rejection must not be counted as a
successful factual answer. Fixed seeds reduce variance but do not prove determinism.
The paired runner executes direct first, then MCP. Timings include model loading,
caching, and MCP startup effects; this fixed-order run is not a controlled latency
benchmark between transports.
`exact_answer_match` is null when either path withholds an answer; two null answers
must not be counted as matching answer text.

The MCP server publishes the canonical `TOOL_SCHEMAS` without regenerating them
from Python signatures. Its SDK `Server` callbacks pass raw argument dictionaries
to the same dispatcher as direct execution. This avoids automatic type coercion
and silent removal of extra arguments. Tests cover bool/string years, invalid
bounds/enums, extra fields, and a real stdio connection. The tested SDK is pinned
to mcp 2.3.0 in requirements.txt.

The fifth tool, `get_filing_section(ticker, year, section)`, reads the preparation
manifest and existing `text.json`/`sections.json`. It returns the complete cleaned
section with original 10-K metadata; it does not parse, embed, truncate, or download.
Selection uses reported fiscal year, not the year of the report or filing date.
Missing, ambiguous, or inconsistent prepared data produces an explicit error.
Long full sections can exceed a small model's context window; targeted questions
should use `search_filings`. Full-section source metadata participates in the
existing answer verification and source footer.

### Paired development run, 2026-10-19

Artifacts: `results/comparison_20261019T164100_100624Z_5dd93bb5.json` and its two
referenced raw result files. All ten cases had equal successful tool payloads and
equal final status between direct and MCP. Initial/final data, index and source-code
fingerprints matched. Each path released eight answers and withheld two; five of
the eight released answers were textually identical. This is transport evidence,
not a claim that ten questions were answered correctly.

Both paths retrieved the correct NVIDIA FY2026 risk source but failed to render
the answer because literal `Item 1A` remained in composer prose. Both paths also
generated a Turkish price-forecast refusal for an English question; the language
check withheld it. These are shared Writer/Critic regression cases for subsequent
orchestration work. The direct Turkish missing-margin reply retained an unresolved
placeholder; refusal and verification wording also need improvement.

`assistant_review` contains Codex's qualitative artifact review. `manual_review`
remains null: independent human grading and the broader golden set are still pending.
The full 236-test suite passed before the final comparison-report change; its four
comparison tests then passed, including the newly added null-answer regression.
All 60 prepared sections were additionally checked against their source offsets
and accession metadata without reparsing or redownloading data.

## Multi-agent completeness diagnostics, 2026-10-21

`diagnostics/full_orchestrator_live_20261021T164418_145115Z.json` captured the original
failure: the financial answer matched its source record, while the mixed answer
listed financial values and filing metadata without summarizing risks. Critic
incorrectly approved that incomplete answer.

Subsequent `answer_completeness_live_*` and `completeness_final_live_*` files record
development attempts, not a success benchmark. With the explicit completeness
verdict, the known incomplete answer was rejected. The correct financial answer
still passed its recorded-evidence recheck. However, repeated Writer attempts
either omitted narrative, violated prose formatting rules, or reached the model's
generation limit. One fresh run also fetched the full section and supplied about
80k serialized evidence characters; this indicates context pressure, not a measured
token count or proof of truncation. RAG instructions now reserve full-section
retrieval for explicit full-section requests.

The experimental prose regex in the generation schema was removed after token-limit
failures. Two temporary `think=false` experiments also failed to establish a reliable
solution; production model settings were not changed. The all-structured-call
experiment in `completeness_final_live_20261021T190248_016481Z.json` additionally exposed
incorrect source attribution that the judge missed, despite withholding the answer
for completeness. Its demand to include every retrieved source was too strict:
the final prompt distinguishes requested-part coverage from exhaustive source coverage.

The final code passed 129 focused tests. These are boundary/flow regressions with
mocked model calls, not proof of model accuracy. There is no successful final live
mixed-answer acceptance to report for this development session. Writer reliability
and claim-to-source judge calibration remain required before CLI integration.

## Limits of the checks

The multi-agent orchestrator now runs Writer then Critic after collecting specialist
evidence. The initial draft and at most two corrections share one revision budget.
Writer JSON/schema/rendering failures and negative Critic verdicts consume this same
budget; they do not start independent repair loops. The Writer receives validation
issues and the rejected response as untrusted revision context. Financial records
and tool evidence remain unchanged, and specialists are not rerun. Model/network
failures still stop execution; Critic errors and exhausted revisions never release
an answer. The CLI remains on the single-agent path until explicit integration.

Exact record insertion prevents the model from changing a selected financial field.
It does not prove that the selected record answers the question, that every narrative
claim is supported, or that every language choice is correct. Those checks still use
a fallible local LLM. Numbers spelled out in prose and semantic contradictions also
remain part of that model-based check. Fail-closed handling can reject valid answers.
Completeness is also assessed by the model, not by deterministic keyword checks.
Its approval still requires independent review of whether the question was answered.

The initial baseline and legacy agent runs used older prompts/settings and only
three cases. They are diagnostic examples, not a controlled performance comparison
with the current verified agent. Re-run both modes on the same dataset and settings
for a new comparison. Keep manual scores separate from the automatic judge.

## Pre-MCP regression review (2026-10-15)

The final test suite passed 204 tests. Selected live observations for all ten case
IDs are indexed in `diagnostics/pre_mcp_review.json`, with manual review notes and
the exact result file used. They span different development runs; they are not a
single controlled benchmark and must not be reported as a general success rate.

The review covers both answer languages, local financial facts, a calculated
margin, explicit missing-input reporting, company resolution, filing citations,
two scope refusals, and a refusal to fabricate a revenue figure. Earlier false
acceptances and false rejections remain in the saved files. In particular, prior
judges mistook record labels for answer language and confused a false assertion
in the question with an answer claim. Verification-only replays live in
`diagnostics/` and are explicitly distinguished from full agent runs.

These examples motivated the structured record renderer, availability cards,
per-run CIK binding, source-free response policy and separate prose language input.
The judge is still fallible and requires broader independent calibration; passing
these regression examples does not prove universal grounding or injection safety.

MCP will change tool transport, not establish correctness. The later multi-agent
work still includes the full Critic revision loop, broader independent judge
calibration, indirect prompt-injection evaluation, and the larger golden set.
