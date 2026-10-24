# Writer repair follow-up — 2026-10-22

The remaining English and Amazon cases were subsequently rerun; see
[2026-10-23 results](remaining_writer_cases_20261023.md).

## Changes

- Normalize the observed Turkish `[Kaynak N]` label to `[Source N]`, preserving
  the ID and retaining source-range validation. The original composition and tool
  evidence remain unchanged. This does not restrict the narrative response language.
- Report exact offending prose spans such as `2025` or `10-K` to the repair loop.
  Financial values still come from selected facts; the prose restriction remains.
- Clarify the Writer prompt: numerical requests may use empty prose, citations use
  the literal Source label, and narrative requests require substantive descriptions.
- Reject citation-only lines before Critic evaluation. This prevents the observed
  empty-risk-bullet failure without relying on the model to detect it.
- Stop appending financial-card citations to unrelated narrative paragraphs.
  Each selected fact card already carries its own citation.

## Live observations

| Run | Seconds | Independent review |
| --- | ---: | --- |
| Turkish Apple revenue | 98.5 | Correct revenue, FY2025 and 2025-09-27; no Writer revision needed |
| First mixed retry | 143.7 | False acceptance: Critic approved empty citation-only risk bullets |
| Mixed retry after empty-line guard and prompt update | 147.0 | Correct revenue and two substantive risk descriptions; one Writer repair |

The last mixed answer describes licensing costs/sales restrictions and disruption
from new strategies, commercial relationships and acquisitions. Each description
matches its designated excerpt. Unlike the earlier draft, it does not claim that
licensing costs cause the sales restriction. Turkish wording for reputation and
acquisitions could still be more precise.

The last answer also exposed an application-generated extra revenue citation at
the end of risk prose. The final renderer change removes that attachment. Offline
re-rendering of the same composition now leaves Source 3 and Source 4 on the risk
descriptions and Source 2 on the financial card. This final layout was not followed
by another full model run; it must not be presented as one.

The previously false-accepted composition is rejected by the current renderer.
This is a specific deterministic regression check, not proof that the Critic now
detects all incomplete or unsupported answers.

## Validation and remaining work

101 focused tests passed across agent verification, Writer, Critic, orchestration
and evaluation. Model settings were unchanged. Raw evaluation artifacts were
preserved. No reindexing was performed.

English numeric and Amazon missing-data cases still need fresh runs with these
changes. Retrieval still returns a mid-sentence fragment for the licensing risk;
preserving sentence context remains a separate next step. The two successful
content checks do not establish broad reliability or a single-versus-multi-agent
performance comparison.

See [structured review and artifact hashes](writer_followup_20261022.json),
[numeric run](../results/multi_agent_mcp_20261022T185100_772827Z_367e21e3.json),
[false acceptance](../results/multi_agent_mcp_20261022T185328_982186Z_a6bab54d.json),
and [last mixed run](../results/multi_agent_mcp_20261022T185719_947062Z_c5ffb639.json).
