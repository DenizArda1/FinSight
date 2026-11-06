# Microsoft revenue/cost comparison — 2026-10-26

> Follow-up: the records-only output was insufficient. See
> [comparison explanations](comparison_prose_20261026.md) for the current fix.

The exact user question was reproduced through the multi-agent MCP path:
“Microsoft'un en son yıllık gelir ve gider maliyetlerini karşılaştır”.

## Cause and changes

The initial run retrieved only revenue: cost concepts were absent from both the
metric configuration and the advertised tool schema. Writer then repeatedly used
`[Fact 2]` instead of a source reference and exhausted its revision budget.

Added `cost_of_revenue` and `operating_expenses` to the existing configuration and
tool contract. Reused the base-metric preparation pipeline for all four companies;
no new SEC downloads were needed. Cost of goods only is deliberately not treated
as total cost of goods and services. Operating expenses remain distinct from cost
of revenue, interest and income taxes. Missing tagged data remain missing.

Planner now treats comparisons between metrics within one company as comparisons
and gathers revenue and both operating-cost categories for the same period.
Numerical comparisons can use source-rendered records without optional prose.
Writer feedback now explicitly rejects ambiguous `[Fact N]` references instead
of treating the fact position as a source ID. Source and number validation remain.

## Verification

425 tests pass, including distinct cost-category retrieval, contract/schema parity
and rejection of fact-position citations. Added the question to the golden set.
The final live MCP run completed in 24.1 seconds and returned all three expected
records for FY2026, 2025-07-01 through 2026-06-30:

| Metric | USD |
| --- | ---: |
| revenue | 331839000000 |
| cost_of_revenue | 106374000000 |
| operating_expenses | 70228000000 |

The values also match the local filing's inline XBRL annual context
`C_29985a27-1d12-4b7e-9a06-156523f6e71e`, scale 6, accession
`0001193125-26-323660`. These are operating-cost categories, not a claim to cover
all expenses. No aggregate expense or difference was calculated by the model.

The AAPL revenue control also completed successfully after the planning change.
This is a targeted regression check, not proof of general model accuracy.

- [Original failure](../results/msft_costs_before_20261026T075701.json)
- [Final verified run](../results/multi_agent_mcp_20261026T080610_486013Z_48ff7689.json)
- [AAPL control](../results/msft_costs_final_20261026T080147.json)
