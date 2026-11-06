# Hybrid Qwen / Luna pilot — 2026-11-06

## Configuration and scope

Planner and specialist tool selection remain on local qwen3:8b. Only Writer and
Critic use gpt-6-luna through Responses, with low reasoning effort, 8192 maximum
output tokens, and store=false. BGE-M3, Chroma, MCP, financial calculations,
prompts, deterministic verification and the two-revision limit are unchanged.
No experimental paragraph repair mode was enabled.

The API key is read from the local ignored .env file and is not included in
configuration snapshots. Role/model settings and API token usage are recorded.
Schema uniqueness is still enforced locally; uniqueItems is omitted only from
the API schema because it is not supported there.

## Validation

- 466 local tests pass, including provider routing, schema translation, refusal,
  incomplete responses, billable usage on incomplete responses and HTTP errors.
- Fresh MCP Microsoft mixed question: two paragraphs, first draft accepted.
  Source 17 supports cloud growth and expense drivers; sources 5 and 10 support
  actual currency effects and conditional macro risks. Financial values match
  the tool records. The wording "uluslararası faaliyet giderleri" is narrower
  than the source's "expenses from our international operations" and remains
  a minor terminology issue; approval does not prove every phrase is exact.
- Apple latest revenue: correct 416161000000 USD, FY2025, 2025-09-27.
- Amazon latest gross margin: correctly explains missing gross profit, does not
  invent a ratio; available revenue is 716924000000 USD, FY2025.
- All three fresh cases completed without revisions. This is a small smoke
  test, not a representative accuracy benchmark.

Same-evidence replay is stored in
`eval/results/hybrid_luna_same_evidence_20261106.json`. Luna Critic rejects the
previous Qwen draft for unsupported currency direction, treating potential
risks as actual events, and misclassifying expenses as revenue. Luna Writer
then produces a grounded two-paragraph response from those same saved tool
results; Luna Critic accepts it. This isolates the model change more closely
than the fresh MCP comparison, whose retrieved sources differ.

## Observed token cost

Standard pricing used: $0.10/M input, $0.01/M cached input, $0.50/M output:
https://developers.openai.com/api/docs/models/gpt-6-luna

| Fresh case | Input | Output (including reasoning) | Estimated USD |
| --- | ---: | ---: | ---: |
| Microsoft mixed | 12788 | 353 | 0.0014553 |
| Apple revenue | 2344 | 120 | 0.0002944 |
| Amazon missing gross profit | 4474 | 158 | 0.0005264 |

These are token estimates excluding tax, not billing receipts. The table covers
only the three fresh questions, excluding the connection probe and saved-evidence
replay. Detailed usage and trace paths are in
`eval/results/hybrid_luna_costs_20261106.json`.

The previous audit's retrieval, comparison-tool, evaluation coverage and amended
filing gaps remain open. This pilot does not close those items or establish that
all Writer/Critic problems are solved.
