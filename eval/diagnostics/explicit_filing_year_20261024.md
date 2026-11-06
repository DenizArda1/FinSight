# Explicit filing-year scope — 2026-10-24

Filing tasks now carry a structured `fiscal_year` into specialist tool execution.
For a fixed-year filing task, the specialist rejects `latest=true`, a missing or
different search year, and an inconsistent `get_filing_section` year before MCP
dispatch. Errors enter the existing tool-feedback loop so the model can retry
with the correct arguments. Arguments are not silently rewritten.

Every newly generated task must contain `fiscal_year`. Filing tasks use the
explicit requested fiscal year or null for latest/unspecified requests. Financial
tasks use null; their period instructions and numerical tools are unchanged.
The Planner is instructed to separate filing comparisons into tasks per period.

## Verification

207 focused tests passed. The new integration fixture contains FY2026 and FY2027
reports in an ephemeral Chroma collection, with FY2027 both latest and closer to
the query embedding. A specialist tasked with FY2026 first attempts `latest=true`:
that call is rejected without dispatch. Its corrected `fiscal_year=2026` request
passes through the real report search, prepared-file checks and context expansion
and returns FY2026. The MCP transport in this fixture is replaced with a local
dispatcher; it is not a live MCP test.

A second case requests absent FY2025 and receives no matches; it does not fall
back to FY2026 or FY2027. Unit tests cover both report tools, strict year types,
the mandatory plan field and separate fixed/latest comparison tasks.

The first live Planner attempt omitted the field despite the conditional schema
requirement. Local validation rejected that response. The final schema makes
the field unconditionally required for every task. A subsequent live call returned
`fiscal_year: 2026` for the original Turkish NVIDIA question in 10.6 seconds.

The live task instruction also contained stray closing/thinking-tag-like text and
was not fully English. The year check passed, but this observation is retained as
a separate model-output-quality issue; it is not a claim that the complete plan
text is clean. The final schema and code did not sanitize that text.

## Limits and next check

The guard enforces the period recorded in the task. Interpreting the user's period
and assigning it to the correct task still depends on Planner output; this is not
a universal deterministic natural-language date parser. The live check exercised
Planner only, not the full MCP/Writer/Critic pipeline. Rerun the original case end
to end to inspect the corrected tool arguments and answer behavior.

See the [live Planner result](explicit_filing_year_planner_20261024T180259_140356Z_215cc0f5.json)
and `tests/test_filing_period.py` for the two-year integration fixture.
