# NVIDIA bilingual evaluation — 2026-10-24

Neither language run delivered an answer. This comparison revealed Writer and
verification reliability problems, not an isolated translation-quality result.
The production code and model settings were not changed during this evaluation.

## Results

| Question language | Application outcome | Seconds | Writer attempts | Critic calls |
| --- | --- | ---: | ---: | ---: |
| English | Execution error | 269.6 | 2 | 0 |
| Turkish | Answer withheld after invalid verdict | 324.1 | 2 | 1 |

Both questions request one export restriction risk from NVIDIA FY2026 Item 1A.
The same model settings and data snapshot were used. The total run took 593.6
seconds. All retrieved text and section bounds were checked against local files.

## English

The specialist searched the requested year and section and retrieved five chunks.
Writer repeated `FY2026` and `Item 1A` in narrative prose, triggering the existing
numeric-prose guard. Its repair call failed with “LLM response is incomplete or
reached its token limit.” No Critic evaluation or released answer followed.
The saved error does not distinguish the exact completion condition: token counts
and `done_reason` were not retained. The internal draft is not a delivered answer.

## Turkish

The specialist used `latest=True`, which happens to select FY2026 in this snapshot,
then requested the full FY2026 Item 1A section. A fixed-year question should not
depend on which year is currently latest.

The full section contains **114842 characters**. The reconstructed initial Writer
prompt is **123917 characters**, compared with **26654** in the English run.
Configured `num_ctx` is 16384 tokens. Character counts are not token counts, and
the trace does not prove actual truncation. This is nevertheless a substantially
different input workload, so language alone is not the isolated variable.

Both Writer drafts were in English. The first also misdescribed the H20 inventory
expense as a charge imposed by the US government; the local report describes an
expense NVIDIA incurred because of excess inventory and purchase obligations.
That draft was rejected for numeric prose before semantic review.

The revised draft discussed many risks beyond the requested export risk. It cited
Source 1 for every narrative point, although that broad regulatory excerpt does
not support all the detailed competition, litigation and governance claims.
The full section was Source 2, and selecting its metadata card did not repair those
claim-to-source links.

Critic returned all flags true, including the incorrect `language_matches=true`,
while filling `issues` with praise and details absent from the revised draft.
The application rejected this inconsistent verdict. Nothing was released, but
this was **verdict-format rejection**, not successful detection of the semantic
and language errors.

## Next step

Run the two languages against identical, bounded evidence at the Writer/Critic
stage. This will remove the retrieval-strategy difference from the comparison.
Then design limits for context sent to the model and improve targeted retrieval
behavior while retaining the full-section tool for appropriate requests.
Record completion/token diagnostics before simply increasing generation limits.

These are two development cases, not a model benchmark. No external SEC audit was
performed, and the large Turkish input does not by itself prove the cause of the
language drift or invalid verdict.

See the [structured review](nvda_bilingual_review_20261024.json),
[paired questions](nvda_bilingual_cases_20261024.json), and
[raw results](../results/nvda_bilingual_multi_agent_mcp_20261024T144127_752034Z_7b4d5b7e.json).
