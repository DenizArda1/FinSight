# Context expansion evaluation — 2026-10-24

The retrieval integration works against the local source files. The released
answer still needs more precise causal wording, despite approval by the Critic.

## Run

- Case: `aapl_latest_revenue_and_risks_tr`
- Mode: multi-agent through MCP; model: `qwen3:8b`
- Duration: 159.9 seconds; two Writer attempts and one Critic call
- Application outcome: completed; all Critic checks passed
- Independent outcome: integration verified; causal qualification needs revision

The source and index snapshot hashes and LLM settings match the previous mixed
run. Code changed, including prompts and citation rendering, so this is not a
controlled measurement of expansion alone. One run cannot establish a speed or
accuracy improvement.

## Evidence and answer review

The revenue card correctly reports 416161000000 USD, FY2025 and 2025-09-27.
Both risk excerpts include additional context under their existing source IDs:

| Source | Original offsets | Expanded offsets | Local validation |
| --- | --- | --- | --- |
| 3: licensing risk | 50611–50869 | 50211–51269 | Exact text match; inside Item 1A |
| 4: new business strategies | 63356–63640 | 62956–64040 | Exact text match; inside Item 1A |

Source 3 now contains the previously missing condition: failure to obtain rights
to use third-party intellectual property, or inability to use it on commercially
reasonable terms. The answer compresses this to licensing causing sales
restrictions. It does not clearly retain the condition, so independent review
requests a wording revision. Critic approval did not catch this loss of precision.

Source 4 supports disruption and unexpected risks from new strategies, commercial
relationships and acquisitions. Turkish wording could improve: use “fikri mülkiyet”
and “satın almalar” instead of “intellektüel mülkiyet” and “alım yatırımları.”

The unrelated revenue citation formerly appended to the risk paragraph is gone.
The two risk descriptions cite Source 3 and Source 4 separately. The first Writer
attempt repeated numbers in prose and lacked substantive risk descriptions;
deterministic validation rejected it, and one repair produced the released answer.

## Next step and limits

Add general guidance for Writer and Critic to preserve conditions and causal
direction, then rerun this case. Do not hard-code an Apple-specific answer.
Expanded character windows still may cut sentences and include neighboring topics.
This is one development case, not a full benchmark or external SEC audit.

See the [structured review](context_expansion_20261024.json),
[raw result](../results/multi_agent_mcp_20261024T103450_988965Z_cb2fdcf2.json), and
[previous mixed run](../results/multi_agent_mcp_20261022T185719_947062Z_c5ffb639.json).
