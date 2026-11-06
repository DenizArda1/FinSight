# Relation-level verification experiment — 2026-10-25

Historical experiment: subsequent NLI integration and its validation are in the
[independent NLI review](nli_review_20261025.md). This page records the unsuccessful
Qwen-only approach, which was not adopted.

The experimental checker is **not integrated into production**. Separately
assessing actor/scope, conditions/certainty, consequence, and causal relation did
not resolve the known NVIDIA geographic-scope false approval. The application
used its existing checks and `qwen3:8b` configuration at this experiment's cutoff.

## Method

`run_relation_checks.py` evaluates the two recorded NVIDIA cases, six new
synthetic relation-transfer controls, and the eight existing regression cases.
The new controls cover transferring a geographic population between supplier
risks, borrowing a condition from a different outcome, and reversing an excluded
customer population. Positive controls include Turkish translations.

The model receives only the claim and cited evidence, without expected labels.
For each dimension it describes the claim and source separately before judging
compatibility. The diagnostic approves only if all four flags are true.
Its source descriptions are model paraphrases, **not verified quotations**.
This experiment evaluates semantic judgment separately from quotation copying;
it is not a replacement for production provenance checks.

The run preserves inputs, prompt, schema, settings, raw responses, errors and
per-case timings in
[`relation_checks_20261025T172938_937920Z_f4a3fef9.json`](../results/relation_checks_20261025T172938_937920Z_f4a3fef9.json).
Errors are never counted as correct rejections. These are development cases,
not an independent benchmark or an estimate of general accuracy.

The completed run had 14/16 expected decisions, one false approval on the real
scope counterexample, and one token-limit/incomplete-response error on the
otherwise supported conditional Turkish translation. Runtime across cases was
496.2 seconds. The new six synthetic controls all matched their labels.

## Decisive observation

For `china_scope_wrong`, the model's actor assessment correctly describes the
claim as including customers in China. Its source assessment correctly states
that the relevant design-out behavior concerns customers **outside China and
other impacted regions**. Nevertheless, it marks these descriptions compatible
and approves the entire claim. There is no quotation-format error in this run.

The faithful counterpart is approved as well. The real pair therefore remains
1/2, including one unsafe false approval. Passing simpler synthetic controls
does not resolve this counterexample.

## Decision and next boundary

Do not adopt this checker or add another production model call based on these
results. Do not describe free-form narrative summaries as reliably verified.
48 focused claim-grounding, Critic and Writer tests passed during this session;
they establish application behavior, not semantic accuracy.

A practical product alternative is a report answer built from verbatim source
passages with company, period, section and filing metadata. Code would retrieve
the selected passage rather than accepting model-rewritten text. This limits
scope-changing paraphrases, but relevance, sufficient context and source
selection still require checks. It also changes the user experience: original
English quotations can appear within a Turkish interface. This alternative has
been presented to the user and **was not selected**. The user chose to preserve
free-form summarization and continue verification work before the interface.

Reproduce the diagnostic without changing project configuration:

```sh
.venv/bin/python -m eval.diagnostics.run_relation_checks
```
