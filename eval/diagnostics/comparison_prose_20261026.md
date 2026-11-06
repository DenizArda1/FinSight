# Comparison explanations — 2026-10-26

The previous cost-comparison fix returned correct sourced records but explicitly
allowed empty prose. That did not satisfy the user's request for a written
comparison. Comparison drafts now require explanatory text in both Writer and
Critic validation. A metadata-only draft cannot be released as a comparison.

For financial comparisons, generation is constrained to prose and source citation
IDs, keeping figures/dates in source-rendered fact cards. The digit constraint
matches the renderer's Unicode-aware digit check: an early run tried Persian
digits and was correctly withheld. A Writer thinking-mode experiment exhausted
its token budget and was not adopted. Production remains Qwen3 8B with think=false.

The application computes ordering only when numeric records share company, annual
start/end and unit. It supplies explicit source-linked relationships and category
names to Writer without raw financial values or dates to repeat. It preserves
original values, metadata and tool traces for rendering and full Critic review.
Mixed scopes fall back to the existing complete-evidence path. No additional
model or per-claim verifier was introduced.

## Validation

430 tests passed. Regression coverage checks nonempty comparison text, source
citations, Unicode digits, equal values, scope mismatches, unchanged original
evidence and source-rendered figures. Both Writer and Critic use the same
comparison contract. The scalar-lookup path remains available.

Final live multi-agent MCP run:
[comparison_prose_20261026T083203.json](../results/comparison_prose_20261026T083203.json)

- Turkish Microsoft comparison: completed in 24.0 s, nonempty sourced paragraph
  stating revenue > cost of revenue > operating expenses. All three expected
  FY2026 records remain below the paragraph.
- English Microsoft comparison: completed in 22.7 s with the equivalent English
  explanation and the same financial records.
- Turkish Apple revenue control: completed in 17.0 s with the expected value and
  fiscal period.

The explanations were reviewed against the numerical source records and were
consistent with their ordering. Terminology and visual presentation can still be
improved. This focused check does not establish general narrative correctness or
coverage for all comparison types. Prior narrative-source limitations remain.
