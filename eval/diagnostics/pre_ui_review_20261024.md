# Pre-UI verification and local-model comparison — 2026-10-24

The code safeguards were strengthened, but the narrative scope problem remains
unresolved. Qwen3 14B was downloaded with user approval and compared with 8B.
It was **not adopted as the production model**. Project settings still select
`qwen3:8b`; the 14B model remains installed and was unloaded from GPU memory after
the comparison.

## Model comparison

| Diagnostic | Qwen3 8B | Qwen3 14B |
| --- | --- | --- |
| Original citation swaps | 4/4 expected decisions, no final errors | 4/4 expected decisions, no final errors |
| Eight synthetic language/scope/causality cases | 8/8, no errors | 8/8, no errors |
| Actual geographic-scope pair | 0/2; both ended in quotation errors | 1/2; the unsupported claim was falsely approved |

The real source says customers **outside China and other impacted regions** may
design out certain U.S. semiconductors. A separate sentence describes reduced
demand in China and other markets. The wrong candidate moved the geographic
scope of the demand statement onto the customer-design decision. Both source
sentences can be quoted accurately without supporting that combined claim.

14B produced valid quotations, but accepted this unsupported combination. The
8B result was withheld because its quotations failed validation; that is not a
correct semantic rejection. Do not aggregate these outcomes into a general
accuracy score or interpret lack of a released answer as correct reasoning.

The four citation-pair runs took about 209 seconds with 8B and 368 seconds with
14B. The synthetic suite took about 82 and 143 seconds respectively. The scope
pair took about 75 seconds with 8B (including failed repairs) and 66 seconds with
14B. These are development diagnostics, not a broad performance benchmark.
The candidate was observed using approximately 11 GB with 100% GPU processing
and a 16,384-token context; this is the model runner's reported resident size,
not total system memory usage.

The [structured review](pre_ui_review_20261024.json) links every compared result.
All failed development runs remain available.

## Changes made

- Semantic assessment is separated from bounded quotation repair. A repair
  cannot replace the recorded decision. A rejection keeps its reason and drops
  unverified quotation text from the verdict; the raw response remains in trace.
- Every accepted quotation must still occur verbatim in its stated source.
  Missing, fabricated or misattributed supporting quotations cannot approve an
  answer.
- Narratives using only source cards are checked against exactly the sources
  selected in those cards. They no longer skip the extra grounding check.
- Paragraphs are checked sentence by sentence. Sources cited collectively must
  support at least one checked sentence, and every sentence must pass. The
  answer is limited to eight report claim sentences before model checks.
- Writer formatting repair edits only prose. Selected facts and response kind
  remain fixed; non-numeric words must be preserved, preventing a repair from
  silently changing “gross margin” into “gross profit.” The existing shared
  revision budget remains in force.
- An oversized full filing section is retained in the raw trace, while the
  specialist automatically makes a real MCP search in the same company, fiscal
  year and section. That additional call consumes the normal tool-call budget.
- Alphanumeric report identifiers such as `H20` are exempted from the prose
  number ban only when they occur literally in report text cited on that line.
  Amounts, fiscal-year labels, dates and percentages remain restricted.
- Double-encoded narrative line breaks are normalized so separate claims do not
  accidentally become a single interleaved citation line.

267 focused tests passed. They verify application boundaries and flow, not model
accuracy. The new model selector arguments affect diagnostic runs only.

## End-to-end observations

The MCP multi-agent path was run on financial, missing-data and filing questions.
Independent review was kept separate from the automatic verdict:

- Apple revenue: the amount, fiscal year, period end and Turkish answer matched
  the retrieved local record.
- Amazon gross margin: the final reviewed answer preserved the metric name,
  reported missing gross profit, and displayed the available revenue correctly.
- NVIDIA export risk: one intermediate automatic approval was rejected on manual
  review because it expanded geographic scope. A subsequent full run withheld
  the answer during quotation verification. No clean final end-to-end narrative
  success is claimed.

These observations span successive code revisions; they are not one clean
benchmark run. The final sentence-level change was unit-tested and probed on
the real scope pair; a fresh full pipeline acceptance after that change has not
been established.

## Remaining work

The unresolved check is the relation between the actor, geographic scope,
condition and consequence—not merely whether the words exist somewhere in a
retrieved excerpt. A larger model alone did not fix it. The next experiment
should verify those linked details against a specific coherent source passage,
with separate controls for borrowing scope from a different consequence.
Keep error withholding and distinguish model judgment from proven source
provenance. Do not declare the pre-UI narrative reliability work complete.

Reproduce the comparison without changing project configuration:

```sh
.venv/bin/python -m eval.diagnostics.run_claim_scope --model qwen3:14b
.venv/bin/python -m eval.diagnostics.run_citation_pairs --model qwen3:14b
.venv/bin/python -m eval.diagnostics.run_claim_regressions --model qwen3:14b
```
