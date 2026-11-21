# Answer contract simplification

Writer now receives short field tokens such as `{{F1_value}}` and
`{{F1_fiscal_year}}`, rather than nested tool-result paths and format modifiers.
The application owns the token-to-source mapping, percentage formatting and
automatic field citations. Unknown tokens still fail validation. Old diagnostic
compositions remain readable through the existing catalog-checked legacy syntax.

Field expansion is performed in the common composition path, not inside Writer.
Single-agent finalization and multi-agent Writer/Critic therefore use the same
mapping. Single-agent composition/verification phases also select the configured
Writer/Critic roles, instead of falling back to the base model.

The UI no longer prints raw internal validation instructions. Failure remains
visible and the full technical reasons remain in diagnostic records. Financial
validation and semantic Critic review remain enabled. Existing paragraph-repair
experiments remain available to their evaluation callers; they are not enabled
by the normal orchestrator.

Validation: 516 Python tests passed, including short-token rendering, exact
percentages, unknown token rejection, single-agent integration and role parity.
Real Writer/Critic calls with the previously captured Intel and Microsoft
evidence passed (one revision each). See `simplified_contract_intel_20261112.json`
and `simplified_contract_microsoft_20261112.json`. These were evidence replays,
not fresh end-to-end retrieval runs. JavaScript execution was unavailable because
the local shell has no Node executable. No Docker rebuild or deployment occurred.
