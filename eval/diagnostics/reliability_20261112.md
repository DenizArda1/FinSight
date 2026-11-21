# Research reliability review — 2026-11-12

## Changes

- A typed specialist budget error preserves collected evidence, allows subsequent tasks to run, and explicitly marks incomplete coverage for Writer. Unexpected service and programming errors still propagate.
- Supplemental excerpt retrieval uses the existing BM25 implementation instead of counting distinct shared words. Exact text offsets and provenance are retained.
- Writer normalizes path separators and missing percent format markers only when the resulting token exists exactly in the fact catalog. Unknown paths and values remain invalid.
- When syntax repairs exhaust the normal revision budget before the first content review, the orchestrator allows at most one reserved content repair. Failed verification still withholds the answer.
- Rejected executor submissions roll back the persisted running job so later requests are not blocked by a phantom job.

## Validation and limits

- 511 Python tests passed. Added coverage for first/later task budget exhaustion, preserved evidence, bounded content repair, withholding failed answers, exact catalog normalization, retrieval ranking, and executor rollback.
- `git diff --check` passed.
- Microsoft annual financials and macro effects passed the real end-to-end MCP run (`reliability_20261112_2.json`).
- Intel end-to-end retrieval completed, but Writer failed validation (`reliability_20261112_1.json`). Subsequent isolated replays exposed formatting and content-review budget problems.
- After the fixes, replaying those same Intel tool results through the actual Writer/Critic orchestration passed (`reliability_20261112_orchestrator_replay.json`, revision count 1). Retrieval and planning were replayed, not rerun, in this final check.
- This is regression evidence, not a production-readiness certification or a guarantee that model responses always pass. No Docker rebuild or deployment was performed.
- Frontend keyboard tests could not run here because `node` was unavailable; no frontend code was changed in this reliability review.
