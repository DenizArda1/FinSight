# FinSight evaluation and verification

Run from the repository root with the local Ollama service available:

```sh
.venv/bin/python -m eval.run_eval --mode single_agent
.venv/bin/python -m eval.run_eval --mode baseline
.venv/bin/python -m eval.run_eval --mode single_agent --case aapl_latest_revenue_tr
.venv/bin/python -m unittest discover -s tests
```

The initial dataset contains ten cases: financial facts, a calculated margin,
company identity, missing data, a filing risk question, two out-of-scope requests,
and a direct instruction to fabricate data. This is a development set, not a
completed benchmark or the later full golden set. Latest-period expectations are
bound to the current local data snapshot; review them after downloading new filings.
The narrative case has an expected claim and source, not an exact answer string.

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
   language. A valid source number alone does not establish support.
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

## Limits of the checks

Exact record insertion prevents the model from changing a selected financial field.
It does not prove that the selected record answers the question, that every narrative
claim is supported, or that every language choice is correct. Those checks still use
a fallible local LLM. Numbers spelled out in prose and semantic contradictions also
remain part of that model-based check. Fail-closed handling can reject valid answers.

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
