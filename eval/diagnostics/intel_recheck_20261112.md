# Intel failure investigation — 2026-11-12

The original run failed after repeatedly retrying an annual-report preparation error, not an API outage. Intel uses named chapters with a Form 10-K cross-reference index. Standard numbered-item extraction found no substantive Item 1. Initial recent-filing searches also omitted query, but recovered on retry. The planner omitted the financial-growth task.

Changes: narrowly scoped named-chapter fallback for MD&A and risks (no invented Business section); stop identical failed tool requests after two executions while retaining failure evidence; clarify mixed financial/recent-development planning and concrete retrieval keywords; distinguish potential-risk claims from realized events in the reviewer; classify UI errors rather than labeling every failure as a connection issue.

Validation: all five downloaded Intel annual reports prepared in memory. 504 unit tests passed; git diff --check passed. First live retry reached verification but failed on a risk paraphrase. Final live retry passed deterministic fields, grounding, language and completeness with supported=true. See intel_recheck_20261112_final.json and its trace_path. This is one successful live regression, not a guarantee of deterministic model behavior. Docker image was not rebuilt.
