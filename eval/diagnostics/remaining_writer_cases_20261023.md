# Remaining Writer regression cases — 2026-10-23

Both targeted cases completed with correct released answers using the unchanged
`qwen3:8b` settings and current Writer/renderer changes. No production code changed
in this session. The source checks below use saved local records, not a fresh SEC audit.

| Case | Seconds | Independent review |
| --- | ---: | --- |
| Amazon gross margin, Turkish | 173.4 | Correct missing-gross-profit explanation, with available revenue and period preserved |
| Apple revenue, English | 85.1 | Correct 416161000000 USD, FY2025, period end 2025-09-27 |

Amazon needed three Writer attempts and two Critic calls. The first repair removed
the forbidden fiscal-year literal from prose. The Critic then rejected an adequate
missing-data explanation as incomplete without identifying a concrete omission;
the period and available input were already in the fact cards. The final answer
passed but repeats the missing-input explanation and duplicates its source cards.
This is a remaining judge-calibration and presentation issue, not a data error.

Apple needed two Writer attempts and one Critic call. After concrete format feedback,
the Writer selected the revenue fact with empty prose. The resulting structured card
answers the English numerical question without a language mismatch.

The first launch failed because Ollama was stopped. Both failures occurred in the
Planner at the local chat connection, before model inference. They are retained as
operational errors and excluded from answer-quality assessment. Ollama was then
started and the same two cases were rerun successfully.

## Next learning step

Implement a bounded context-window helper in `src/rag/context.py`, using the
existing absolute chunk offsets and section bounds. Load the matching local report
and verify identity/offset consistency when integrating it into retrieval later.
Keep retrieved and expanded ranges distinguishable. This can supply surrounding
evidence without rebuilding embeddings. A fixed character window alone does not
guarantee complete sentences; sentence-boundary handling remains a later step.

- [Successful run](../results/multi_agent_mcp_20261023T131341_739053Z_2ab6de8f.json)
- [Startup failures](../results/multi_agent_mcp_20261023T131303_788933Z_ae8fe471.json)
- [Independent review, source hashes and settings](remaining_writer_cases_20261023.json)

Two successful cases do not establish general accuracy or reliable Critic decisions.
