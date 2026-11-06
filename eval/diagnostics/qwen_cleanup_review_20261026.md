# Qwen-only prototype review — 2026-10-26

NLI, its local weights/configuration, per-claim/passage model passes, special prose repair and experimental runners were removed at the user’s request. Historical results are retained as historical evidence. Qwen3 8B handles planning, retrieval decisions, writing and Critic review. BGE-M3 remains solely for the existing vector index.

The runtime keeps deterministic financial/source rendering and one Qwen Critic pass per draft, with at most two Writer revisions. It does not establish the truth of every narrative claim.

## Fixes and first interface

- Shorter, bounded planner instructions; preserve calculation tasks instead of retrieving only their inputs.
- Do not execute identical successful specialist requests repeatedly; empty records remain valid missing-data evidence.
- A typed output-limit failure after retrieval preserves tool evidence for Writer/Critic review. The unfinished model response is discarded. Specialist output is capped at 1024 tokens; the shared config is not mutated.
- Out-of-scope plans constrain Writer to refusal; narrative citations must appear in the explanation rather than only in metadata cards.
- Streamlit uses the existing multi-agent MCP runtime. It provides ticker/question inputs, answers, source metadata and expandable original excerpts, explicit unverified drafts, and new Markdown files under reports/.
- Required disclaimer is present in the interface, CLI and exported notes.

## Validation

422 unit/integration-style tests pass, including mock UI success/error/withheld paths, source-excerpt display and safe export. pip check reports no broken requirements. Streamlit’s local health endpoint returns HTTP 200. Browser automation was unavailable; no visual browser QA is claimed. The 25-question dataset passes structure validation; it was not fully rerun.

**The table uses the latest relevant run for each of six development questions across iterations. It is not a single final-version benchmark.** The final specialist budget/recovery change was live-retested on the AAPL revenue and Turkish risk questions; its truncation branch is also covered by a mocked regression test.

| Question | Runtime | Seconds | Assistant source review |
| --- | --- | ---: | --- |
| aapl_latest_revenue_tr | completed | 15.0 | pass |
| amzn_missing_gross_margin_tr | completed | 29.0 | pass |
| aapl_net_margin_tr | completed | 59.4 | pass |
| nvda_export_risk_en | completed | 86.1 | pass |
| refuse_buy_advice_tr | completed | 6.9 | pass |
| nvda_export_risk_tr | completed | 78.8 | fail |

**Observed quality: five examples satisfy the reviewed expectations; the Turkish narrative does not.** This small, repeatedly used development set is not a general accuracy estimate. A completed run or Qwen Critic approval must not be equated with an independently correct answer.

The remaining Turkish error is concrete: the use/resale/repair/transfer claim is not supported by its cited Source 1, and the China-law restriction claim is linked to Source 3 instead of a supporting passage. Qwen Critic falsely accepted it. The first UI therefore exposes original excerpts and does not label model approval as a guarantee. No additional verifier model was introduced.

Latest runs:

- [qwen_prototype_20261026T072632_9b2dee41.json](../results/qwen_prototype_20261026T072632_9b2dee41.json)
- [qwen_citation_scope_20261026T073209_16353fe3.json](../results/qwen_citation_scope_20261026T073209_16353fe3.json)
- [qwen_recovery_20261026T073816_8a0677dd.json](../results/qwen_recovery_20261026T073816_8a0677dd.json)

Financial checks: AAPL revenue 416161000000 USD, FY2025 ending 2025-09-27; net margin 26.92%. AMZN gross_profit is absent for the requested period; its available revenue is preserved. The corrected English narrative preserves “outside China” and its citation. The advice example explicitly declines the request.

Next work is normal prototype development: improve the interface with user feedback and keep the failed narrative as a regression example. General semantic correctness, full evaluation targets, hybrid retrieval and deployment remain unproven or pending.
