# Writer / Critic report-contract review — 2026-10-29

The project report (pages 7–8) assigns Writer source-cited prose with field
placeholders, and Critic numerical/source/semantic checks plus bounded revision.
It does not require numerical data to appear only in cards or rejection based on
paragraph count.

Changes:

- Removed financial-value hiding, ordering-only payloads, and the prose-wide
  numeric regex in the composition schema.
- Writer receives original financial records and report excerpts, with exact
  inline field references in its catalog. Only catalog fields can be inserted;
  each inline field requires its source citation in the same paragraph.
- Exact FY labels, filing dates, forms and section labels are bound to fields
  from sources cited in the same paragraph. Wrong metadata and raw financial
  amounts remain rejected. This avoids wasting revisions on a correct `FY2026`.
- Existing renderer still rejects unbound figures, invalid fields, missing or
  omitted sources. Calculations remain tool outputs, never Writer calculations.
- Replaced separate mixed/comparison prompt branches with one writing contract.
  Two or three paragraphs are a writing preference, not an approval criterion.
- Critic checks facts, meaning, scope, language, coverage, advice and injection.
  Negative flags without explanations now produce revision feedback. Positive
  flags with reported issues cannot release an answer.
- Retained one Qwen judge per draft, at most two revisions, existing tools,
  retrieval, exports and UI. No new model or validation layer was added.

Validation:

- 438 automated tests passed, including inline rendering, provenance/tampering,
  malformed responses, and bounded revision after an incomplete Critic verdict.
- Early saved-evidence replay produced a semantic error that Qwen approved.
  A second replay produced English prose for the Turkish question and a
  contradictory review. These are failures, not successful evaluations.
- A temporary `think=true` Critic probe did not consistently solve those problems.
  Production model settings were not changed. Artifacts:
  `../results/writer_inline_initial_20261029.json`,
  `../results/writer_inline_replay_20261029.json`,
  `../results/critic_thinking_review_20261029.json`.

Unit tests establish contract/flow behavior, not model faithfulness. Critic
approval alone must not be reported as proof that every claim is correct.

Final live outcome:

- The full MCP request first exhausted revisions on a correct literal `FY2026`;
  this exposed the metadata-binding fix above. The state is recorded in
  `../results/writer_report_contract_mcp_20261029.json`.
- Replaying its exact successful tool evidence with the final code produced a
  Turkish draft on the last permitted attempt. Source-field checks passed and
  Qwen approved it. Assistant review failed it: the draft inferred an FX effect
  from cost-of-revenue data and omitted operating expenses. See
  `../results/writer_report_contract_replay_final_20261029.json`.
- Therefore the excessive presentation restrictions are addressed, but the
  Microsoft mixed question is NOT a successful semantic regression. The current
  Qwen Writer/Critic pair still has a demonstrated false-approval limitation.
  No additional verifier, model switch, or prompt experiment was added to hide it.
