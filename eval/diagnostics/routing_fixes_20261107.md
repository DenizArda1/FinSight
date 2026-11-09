# Routing and calculation-contract fixes — 7 November 2026

## Changes

- Planner now explicitly treats company identity/CIK as supported financial work,
  preserves requested calculations, distinguishes narrative from mixed tasks, and
  asks for missing company/margin information. Examples cover different routes.
- Financial specialists are not offered `get_company_facts` or `compute_metrics`
  until company resolution succeeds. Existing execution-time CIK validation remains.
  `compare_companies`, which resolves its own companies, remains available.
- Filing guidance maps business descriptions to Item 1, risks to Item 1A, and
  financial/macro effects to Item 7.
- `compute_metrics` exposes its configured calculation definitions. Writer/Critic
  distinguish an unavailable configured result from mathematical impossibility.
  Gross margin still requires reported gross_profit under metrics.yaml. No new
  cost-based derivation or LLM arithmetic was introduced.
- A clarification route permits only a clarification composition with no fact cards.
  Writer/Critic check missing user intent instead of accepting an assumed company
  or treating missing intent as missing financial data.
- Language instructions now cover both directions explicitly and remove the
  Turkish-only terminology cue from the otherwise language-neutral Writer prompt.

No model/provider change, new agent, NLI, external language detector or new
retrieval component was added.

## Executed iterations (all retained)

| Result file in `eval/results` | Cases | Observation |
| --- | --- | --- |
| `multi_agent_mcp_20261107T160545_050094Z_b9094353.json` | 8 | Seven useful expected responses; missing-company question still attempted placeholder identifiers. |
| `multi_agent_mcp_20261107T160919_445784Z_b046b568.json` | 3 | Planner chose clarification but Writer gave a lack-of-evidence answer; ambiguous margin regressed to net margin. |
| `multi_agent_mcp_20261107T161123_742034Z_e9700365.json` | 4 | CIK, growth and both clarification cases answered as expected after the clarification contract fix. |
| `multi_agent_mcp_20261107T161304_249890Z_8a083f80.json` | 5 | English Amazon answer reverted to Turkish. Microsoft financial calls skipped resolution and failed; RAG searched Item 1. Released answers were not counted as successes on those cases. |
| `multi_agent_mcp_20261107T161655_926327Z_2bc7dee2.json` | 5 | Final targeted cases below behaved as expected after tool gating, section guidance and language changes. |

## Final targeted checks

These are assistant inspections of saved answers and tool traces, not human
calibration or an independent new 37-case benchmark.

| Case | Observed final behavior |
| --- | --- |
| Amazon gross margin, English | English answer accurately states the missing reported-gross-profit input; no invented margin. |
| Apple annual revenue growth | Python `compute_metrics` result used: 6.43%, FY2024 to FY2025, correct revenue inputs. |
| Unspecified company | Asks which company instead of guessing or claiming data is missing. |
| Unspecified Apple margin | Asks which margin rather than choosing net margin. |
| Microsoft revenue/costs/macro | Resolves MSFT first, retrieves all three financial metrics, searches Item 7, and releases two supported Turkish paragraphs. |

The Microsoft answer uses FY2026 revenue 331839000000 USD, cost of revenue
106374000000 USD and operating expenses 70228000000 USD. Source 7's expanded
context supports increased reported revenue from currency fluctuations, no
material effect on international expenses, and conditional economic/trade risks.
The observed answer preserves those distinctions. Its elapsed time was 53.36 s.

All 479 unit/regression tests passed after the final production changes;
`git diff --check` passed. Earlier failed live iterations remain in the record.

## Remaining work

- The five final cases are not a replacement for the full 37-case evaluation;
  do not merge successful cases across different prompt revisions into one score.
- Revisit the Apple business and Microsoft competition source-expansion failures
  from 6 November, then repeat the full frozen question set.
- Planner still sometimes splits calculations into redundant retrieval tasks.
  This run fixed the missing calculation result, not all efficiency problems.
- Language correctness in one final run does not prove repeatability.
- Explicit Critic security warnings and actual human review calibration remain open.
- Raw large-number formatting and duplicate supporting cards still need presentation
  refinement; none was silently treated as fixed here.
