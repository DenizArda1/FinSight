# Report-to-code coverage — 6 November 2026

Scope: the PDF's Basic + Target implementation, with the user's explicit choice
of Qwen planning/specialists, Luna Writer/Critic and local BGE-M3. Advanced
features are optional and excluded. This is an implementation report, not a claim
that the PDF's quality thresholds or delivery conditions have been achieved.

| PDF requirement | Implementation | Status |
| --- | --- | --- |
| SEC cache, throttle, retry, User-Agent, annual originals/amendments | `src/ingestion/edgar.py`, `scripts/download_edgar.py` | Existing |
| Metric contract, three revenue tags, unit/period/latest-filed selection | `configs/metrics.yaml`, `src/data/explore_facts.py` | Existing; provenance notes expanded |
| Growth, margins, CAGR computed in Python | `src/pipeline/run_metric_pipeline.py` | Existing; calculated rows now retain fiscal year |
| Multi-company comparison | `src/tools/financial_metrics.py:compare_companies`, schemas/registry | Added; common source-year window, exact company fiscal dates, missing inputs explicit |
| Own stdio MCP server consumed by agents | `src/mcp/server.py`, `src/agents/runtime.py` | Six tools, including comparison |
| Section parsing, metadata and source offsets | `src/rag/sections.py`, `chunking.py`, filing pipeline | Original sections strict; partial amendments supported |
| 10-K/A precedence without replacing unrelated sections | `src/rag/versions.py`, report search, preparation summary | Newest filed available section per company/period; full section reads use same policy |
| Hybrid BM25 + dense, RRF, company/year/section filters | `src/rag/hybrid.py`, `retrieval.py` | Implemented and used by `search_filings` |
| Index/query embedding compatibility | `src/rag/index_identity.py`, embedding pipeline | Model/digest verified; legacy relabelling refused; rebuild path implemented |
| Incremental synchronization and stale record removal | embedding pipeline, vector store | Unchanged vectors reused; stale reports/chunks removed after successful preparation; incomplete index blocks queries |
| Planner, Data, Filing, Writer, Critic and bounded revision | `src/agents/*` | Existing roles preserved; no new agent/verification layer |
| Deterministic numeric fields, source identity, advice/prompt boundaries | `src/verification/*`, prompts | Existing checks preserved; claims still require semantic evaluation |
| Fiscal year, filing/form/accession/tag/section provenance | source reference rendering and tool metadata | Expanded, including amended-value/section explanations |
| UI, fixed disclaimer, source panel, local new-file Markdown export | `src/ui.py`, `src/reporting.py` | Existing; token/cost display added |
| Per-step token/API-cost/latency traces | `src/llm/usage.py`, clients, runtime, eval | Added cost aggregation; unknown/missing usage is not presented as measured zero |
| B0 and B1 code, final comparison table | `eval/naive_rag.py`, `run_suite.py`, `report_results.py` | Three 37-case development runs executed; see `luna_evaluation_20261106.md` |
| Automatic metric scoring and human-judge calibration | `eval/score_results.py`, `calibrate_reviews.py` | Automatic scoring executed; human calibration remains pending and judge disagreements are documented |
| Indirect injection in an index COPY | `eval/injection_fixture.py`, `run_injection.py` | One exposed attack resisted; explicit Critic security warning missing; full requirement not passed |
| Deployment packaging | `Dockerfile`, `.dockerignore`, README | Recipe prepared, not built/published; host must provide Ollama and data |

## Data and integration evidence

- Reprepared 20 local original reports; 60 sections / 2702 chunks.
- Built `filing_sections_bge_m3_v2` with the actual local BGE-M3 model digest;
  retained v1. Then reran synchronization using existing vectors successfully.
- Real MCP discovery advertises six tools. Three-company revenue growth,
  net-margin and CAGR comparison returned 18 source-backed rows for a common
  three-source-period window.
- Real hybrid MSFT Item 7 search returned three filtered matches with both dense
  and BM25 ranks; complete Item 7 retrieval succeeded. No answer-generating LLM
  calls were used for these integration checks.
- Evidence: `code_smoke_20261106.json`. Local regression suite: 477 tests pass;
  compile, diff whitespace and installed dependency checks pass.

## Remaining final evaluation and delivery work

1. The set is now 37 cases; 20 raw-data numeric checks found no mismatch.
   Resolve documented narrative-rubric and missing-gross-profit contract ambiguity
   before claiming a final calibrated benchmark.
2. Initial B0/B1/final runs, five advice cases, three direct attacks and one
   isolated indirect attack are executed. Fix the routing, calculation, language,
   source-expansion and security-warning issues in `luna_evaluation_20261106.md`,
   then rerun affected cases and the unchanged comparison set.
3. Obtain at least ten independently human-labelled examples; run calibration,
   publish measured accuracy/citation/faithfulness/refusal/injection figures,
   and write at least five concrete error analyses.
4. Build/verify the deployment image on the selected host and publish a demo and
   technical article. No public deployment or external publication was performed.

No NLI, reranker, knowledge graph, TCMB integration, fine-tuning or PDF export was
added. The experimental paragraph-repair code remains inactive. Free-form
summarization is retained; model judgments are not treated as ground truth.
