# Full MCP evaluation after evidence limits — 2026-10-24

The Turkish NVIDIA question completed in 104.4 seconds. The answer is in Turkish
and directly supported by the cited FY2026 Item 1A excerpt. It satisfies the
current minimal expected claim, although its explanation remains generic.

## Observations

- One `search_filings` call returned one broad regulatory-risk excerpt.
- There was no `get_filing_section` call in this run.
- Writer made two attempts: the first repeated `FY2026` and `Item 1A` in prose;
  the deterministic check triggered a repair that retained these in the source card.
- Critic approved the repaired answer. Independent review found its limited claims
  supported: restrictions on product exports may adversely affect NVIDIA's business.
- The cited source is the intended `0001045810-26-000021` filing. The chunk and
  expanded context exactly match local text and remain inside Item 1A.

The model received 1286 characters of report text (original and expanded text
counted together), below both limits. No sources were omitted. This live run
therefore **does not exercise or prove the omission branch**; that branch has the
offline replay and unit-test coverage documented separately.

## Remaining issue

The tool call used `latest=True` rather than `fiscal_year=2026`, despite the explicit
year in the question. The latest indexed report currently happens to be FY2026,
so this run returned the right report. That behavior is not robust when newer data
arrives. The next correction should preserve the user's requested year, with a
test where the latest report is different from the requested year.

The final answer is a short paraphrase of a broad risk statement. It does not
explain an operational mechanism such as lost sales or demand shifting to rivals;
those details were not present in the selected excerpt, and the answer did not
invent them.

## Comparison limits

The source snapshot, index snapshot and model settings match the earlier Turkish
run, which took 324.1 seconds and withheld its answer. Retrieval behavior changed:
that run fetched a full section and this one did not. The speed difference cannot
be attributed solely to the evidence budget. This is one development observation,
not proof of general reliability or an external SEC audit. Production code was not
changed during this evaluation.

See the [structured review](evidence_limits_live_20261024.json),
[raw MCP trace](../results/bounded_evidence_multi_agent_mcp_20261024T175203_623503Z_868e5030.json),
and [offline limit checks](evidence_limits_20261024.md).
