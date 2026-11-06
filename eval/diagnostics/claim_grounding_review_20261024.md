# Claim grounding review — 2026-10-24

This is the earlier development checkpoint. See the [subsequent pre-UI review](pre_ui_review_20261024.md)
for later fixes, real-pipeline failures and the completed 8B/14B comparison.

The original failure is real: Critic approved a claim attached to a source that
did not establish its specific mechanism. A valid source number does not prove
that the source supports the claim. The baseline accepted both deliberately
wrong citations in two controlled pairs.

The new gate is integrated, but semantic reliability is **not resolved**. The
latest run withheld both wrong-citation answers, but also rejected one correct
answer and encountered one verification error. Do not report this as a clean
four-case pass or as completion of Critic evaluation.

## Implementation

- `src/verification/claims.py` binds cited report prose to only its cited sources,
  retaining original source IDs. Lines citing the same source set share a check.
- The model must provide short supporting quotations and identify missing
  details. Code verifies that each quotation occurs verbatim in its stated
  source. An approval requires a quotation from every cited source and no
  missing details. Quotes are limited to 300 characters.
- A malformed verdict receives at most one format repair with unchanged
  evidence. Transport/incomplete-response errors are not silently approved.
- Both multi-agent Critic and single-agent finalization use this gate after
  existing deterministic and general semantic checks.
- In orchestration, an unsupported verdict goes back to Writer through the
  existing bounded revision loop; a verification error withholds the answer.
- Writer is instructed to put report claims on separate lines, with their
  citations together. Interleaved citation groups are rejected for repair.
- Pure financial fact paths do not add this report-specific model call.

The gate does not prove semantic entailment merely by finding an exact quote.
Uncited prose still relies on the general Critic. Eight distinct report citation
groups are allowed, so the added model calls have a latency cost.

## Final production-code comparison

Model: `qwen3:8b`, unchanged settings. Same recorded tool evidence and source IDs;
only the citation differs within each pair. Expected labels are not sent to the
model. Recorded context is checked against local source files first. These are
development counterexamples, not a held-out evaluation or a new end-to-end MCP
run.

| Claim / citation | Expected | Outcome | Released? |
| --- | --- | --- | --- |
| Shipping/services, Source 4 | Supported | Passed | Yes |
| Shipping/services, Source 1 | Unsupported | Rejected: missing shipping/service support | No |
| R&D roadmap, Source 3 | Supported | Incorrectly rejected after quote repair | No |
| R&D roadmap, Source 4 | Unsupported | Verification error: non-verbatim quote | No |

Two of four semantic decisions matched the expected labels. Only one of two
correct answers was released. No wrong-citation answer was released, but the
verification error must not be counted as a correct semantic rejection. Total
time for all four independent Critic calls was approximately 188.5 seconds.

The supported R&D statement was rejected because the model treated a faithful
general paraphrase of deemed export limitations as a wording mismatch. This is
an overly strict semantic judgment, not missing local data.

## Experiments retained

Filtering the general Critic to only cited evidence did not fix either wrong
acceptance. A narrow quote-based check rejected both wrong cases in an early
probe, but later integration exposed quotation copying and output-limit errors.
One intermediate run was interrupted after two saved results and is explicitly
excluded as a complete comparison.

Selecting passage IDs eliminated copying errors but reintroduced one wrong
acceptance; that experiment was reverted. Short verbatim quotations remain in
the current implementation. All runs, including failures, are linked in the
[structured review](claim_grounding_review_20261024.json).

## Validation and remaining work

251 focused tests passed. Coverage includes source isolation, fabricated or
misattributed quotations, strict verdict consistency, bounded repair, withheld
answers on errors, single-agent integration, and Writer revision after a failed
claim check. These unit tests do not establish model accuracy.

The remaining work is semantic acceptance reliability: supported paraphrases
must pass while the wrong-source controls remain rejected. Further prompting on
these same four cases alone would risk tuning to the examples. A broader,
independently reviewed set and a stronger Critic candidate should be compared
before claiming this problem is solved. Installed models were checked: only
`qwen3:8b` and the `bge-m3` embedding model are available. No new model was
downloaded and no UI changes were made.

See [raw final results](../results/citation_pairs_20261024T184021_584024Z_e039adb8.json)
and [runner](run_citation_pairs.py).
