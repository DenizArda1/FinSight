# Targeted multi-agent review — 2026-10-22

This records the initial batch. Subsequent changes and reruns are documented in
[Writer repair follow-up](writer_followup_20261022.md).

Four real multi-agent cases ran through MCP using the existing `qwen3:8b`
configuration: temperature 0, context 16384, generation limit 4096, request timeout
180 seconds. Ollama was started locally. The mixed question used `bge-m3:latest`
for query embedding against the existing index; no report reindexing was performed.
Application code, prompts, and model settings were not changed during these runs.

## Results

| Case | Seconds | Outcome | Final blocking issue |
| --- | ---: | --- | --- |
| Apple revenue and risks, Turkish | 166.3 | Withheld | Localized `[Kaynak N]` citations |
| Apple revenue, Turkish | 107.5 | Withheld | Localized `[Kaynak N]` citations |
| Amazon missing gross margin, Turkish | 142.3 | Withheld | Fiscal year repeated in prose |
| Apple revenue, English | 102.5 | Withheld | `10-K` repeated in prose |

Total case time was 518.6 seconds. All four cases exhausted the initial Writer
attempt plus two revisions: 12 Writer calls, zero Critic calls, zero released
answers. These are availability failures, not successful answers merely because
unsupported output was withheld. This small targeted set is not an overall model
accuracy benchmark or a comparison with single-agent execution.

## Findings

1. **Source retrieval worked for these cases.** Apple revenue was 416161000000 USD
   for FY2025, ending 2025-09-27. Amazon revenue was available for 2025-12-31 and
   gross profit was missing. The local files agreed with these tool results.
   The mixed case's reference file hashes matched the golden set. This is a local
   data consistency check, not a new external audit of SEC filings.
2. **Writer formatting prevents delivery.** The renderer recognizes `[Source N]`
   and excludes those citation digits from its prose-number check. It does not
   recognize `[Kaynak N]`. Both Turkish Apple repairs kept those labels, producing
   a generic numbers/dates error rather than actionable citation-format feedback.
   Replacing only the labels in copies of the final compositions passed deterministic
   rendering. This offline diagnostic did not call the Critic, change production
   behavior, or establish semantic correctness.
3. **The issue is broader than citation language.** Amazon kept the correct fiscal
   year in prose despite feedback; the English Apple repair retained `10-K`.
   These values belong in the selected fact cards under the current contract.
   The repair loop repeatedly failed to meet that contract even with correct data.
4. **The mixed draft needs semantic repair too.** Source 3, chunk
   `0000320193-25-000079:item_1a:25`, begins mid-sentence. The full local report
   explains that failure to obtain intellectual-property rights can prevent sales
   and expose the company to licensing costs. The Writer instead describes
   licensing costs as causing the sales restriction. The second risk concerns
   disruption from new strategies, commercial relationships and acquisitions.
   Citation-label normalization alone does not resolve the first claim's causality.
5. **Critic quality remains unmeasured in this batch.** All cases failed before the
   Critic. The saved verification method name must not be interpreted as proof
   that an LLM judge actually evaluated these candidates.

## Next development step

Make citation handling and Writer feedback more precise while preserving exact
financial-field insertion. Consider structured citation IDs rendered by the
application, and specific feedback identifying prohibited prose spans. Preserve
sufficient sentence context for narrative retrieval. Add focused regression tests,
then rerun these cases and independently review any released answer before
expanding to the full development set. These are proposed changes, not implemented
fixes in this evaluation session.

## Artifacts

- [Mixed case](../results/multi_agent_mcp_20261022T182708_833140Z_64a8cfc3.json)
- [Turkish numeric and missing-data cases](../results/multi_agent_mcp_20261022T183019_014316Z_88b699d9.json)
- [English numeric case](../results/multi_agent_mcp_20261022T183445_862876Z_1ad4ea3d.json)
- [Independent review with hashes and diagnostics](multi_agent_review_20261022.json)

Raw run artifacts are unchanged; independent review is stored separately.
