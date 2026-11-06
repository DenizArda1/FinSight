# Explicit fiscal year: full MCP check — 2026-10-24

The period-scope correction worked in the live pipeline. Claim-to-source support
still needs improvement: Critic approved a narrative with attribution weaknesses.

## Verified behavior

- Duration: 188.7 seconds, two Writer attempts and one Critic call.
- Planner recorded `fiscal_year=2026`.
- The real MCP `search_filings` call used `fiscal_year=2026`, `section="Item 1A"`
  and `top_k=5`; it did not use `latest`.
- All five retrieved chunks belong to filing `0001045810-26-000021`, FY2026.
- The report-text budget retained 11710 characters across Sources 1–4 and omitted
  Source 5. Source IDs remained stable, and the answer did not cite the omitted source.
- Admitted chunk text, expanded context and section bounds match local report files.
- The final answer is Turkish. One repair removed fiscal/section labels from prose.

The current real index has FY2026 as the latest report for NVIDIA. A newer FY2027
report versus a requested FY2026 report was tested in the earlier integration
fixture, not this live data snapshot.

## Independent answer review

The first bullet cites Source 1 for US/foreign economic-security policies affecting
product sales and service delivery. Source 1 is a broad regulatory-risk statement;
the explicit shipping/services and government-policy discussion is in Source 4.
The claim's existence elsewhere in the evidence set does not fix the wrong citation.

Source 2 supports the second bullet about demand, excess inventory and financial
burdens. Source 3 supports the third bullet about R&D plans.

The fourth bullet cites Source 4 for noncompliance leading to penalties and business
restrictions. Penalties are explicit there, but specific business restrictions are
not. Source 3 discusses business restrictions in a different China/Mellanox
regulatory context. Those source conditions should not be combined casually.

Critic approved all checks. This is therefore a pass for period propagation and
budget behavior, **not a clean independent answer-quality pass**. The Planner task
also retains stray closing/thinking-tag-like text; it did not prevent correct year
propagation but remains a separate output-quality issue.

## Next step

Build focused claim-to-source checks using faithful claims and deliberately wrong
source assignments. Evaluate whether Critic rejects mismatches before changing
verification behavior. Valid source numbers alone do not establish support.

Production code was unchanged during this run. Source/index snapshots and model
settings match the previous run, but retrieval count changed, so duration is not
a controlled performance comparison. No external SEC audit was performed.

See the [structured review](explicit_filing_year_live_20261024.json),
[raw trace](../results/explicit_year_multi_agent_mcp_20261024T180557_478219Z_2dadfb40.json),
and [implementation checks](explicit_filing_year_20261024.md).
