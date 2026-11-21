# Focused corrections — 18 November 2026

No new agent, external service, or model was introduced.

- Cited financial-year fields can bind natural apostrophe forms such as `2025’te`.
  Comparative year labels in cited report text also support these forms. Free
  monetary values and absent years are still rejected; Critic checks meaning.
- Removed the blanket requirement to cite a narrative report merely because a
  planner chose `mixed`. Citations are still validated and Critic still checks
  each claim against its source. This fixes the recorded Apple false rejection.
- Shortened planner instructions and required `filing_scope` and `years` in new
  plans. Annual scope hides and rejects supplemental quarterly/event tools;
  unspecified annual search periods use latest annual retrieval.
- Financial tool calls inherit minimum source-year coverage from the plan.
  Financial tasks share the plan's maximum requested coverage so ingredient
  tasks cannot silently reduce a requested two-year comparison to one year.
  Actual adjusted arguments are recorded in the tool trace. Invalid types are
  not silently coerced.
- Specialists receive the original question as well as their task so omitted
  metric requests are not lost in a planner paraphrase.

Validation: 521 Python tests passed; `git diff --check` passed. The exact saved
Intel and Apple failed drafts now pass deterministic rendering and real Critic
review (`focused_review_20261118.json`). No prose rewriting was needed in those
two regressions.

Three local Qwen planner checks are saved in `focused_plans_final_20261118.json`.
They select annual scope for NVIDIA and include two-year comparison coverage for
Apple/Amazon. The planner still creates redundant financial tasks and sometimes
omits a metric from an individual instruction. Original-question propagation and
minimum coverage address downstream information loss, but a new end-to-end run
has not yet demonstrated stable completion or improved latency. This is not a
new 5/5 benchmark result. The 15-minute five-case test was not repeated.

Ollama was initially stopped and was started for the three short local checks.
No Docker image was rebuilt or deployed.
