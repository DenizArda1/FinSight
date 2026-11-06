# Causal grounding follow-up — 2026-10-24

The revised prompts produced a useful Critic rejection and Writer repair in this
run. The final answer still has a terminology problem, so approval is not treated
as complete semantic correctness.

## Changes and validation

Writer now receives general instructions to retain material conditions, causal
direction, negation and uncertainty. Critic must identify the specific claim,
source and changed condition when these do not match. Faithful paraphrases remain
acceptable. No Apple-specific answer or glossary was added.

102 existing focused tests passed. The prompt diff passed the whitespace check.
The user's existing runtime comment edit was preserved.

## Live run

- Case: `aapl_latest_revenue_and_risks_tr`, multi-agent through MCP, `qwen3:8b`
- Duration: 214.2 seconds (previous run: 159.9 seconds)
- Writer attempts: three; Critic calls: two; both permitted revisions used
- Application result: completed, final verification passed
- Independent review: causal repair demonstrated; translation issue remains

The local source and index hashes, model settings and tool evidence match the
previous run. Both expanded excerpts still match the local report exactly and
remain inside Item 1A. This is a single development comparison, not a benchmark.

The initial Writer response repeated financial numbers in prose and introduced
an unsupported claim about copyright issues associated with local data usage.
The deterministic check rejected the numeric prose. The next response removed
the numbers but kept the unsupported claim.

Critic then rejected the first risk, correctly explaining that Source 3 concerns
third-party intellectual property rights, not local data usage. Writer revised
the risk to explicitly say that licenses cannot be obtained, with possible product
or service modifications and licensing costs. Critic accepted the revised answer.
The final revenue card correctly reports 416161000000 USD, FY2025 and 2025-09-27.

## Remaining limits

The second risk translates acquisitions as “alım-satım yatırımları.” This can
suggest trading or sales rather than company acquisitions; “şirket satın almaları”
would preserve the source meaning better. Critic did not flag this. “Fikri mülkiyet”
would also be more natural than “intellektüel mülkiyet.”

The run demonstrates detection of a new unsupported claim, not rejection of the
exact ambiguous answer from the previous run. It does not isolate Writer changes
from Critic changes, and all revisions were needed. Broader bilingual testing is
the next step; do not infer general reliability or a speed trend from this case.

See the [structured review](causal_grounding_20261024.json),
[raw trace](../results/multi_agent_mcp_20261024T103957_562801Z_0fc74c57.json), and
[previous review](context_expansion_20261024.md).
