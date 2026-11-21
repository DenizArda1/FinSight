# Comparative fiscal year regression

The failed UI run is `logs/runs/20261112T183322001597Z_549d76f0.json`.
Its last Writer composition correctly described net income in FY2025 versus a
net loss in FY2024, citing Source 14. The report body explicitly contains both
years, but its metadata only declares FY2025. The deterministic checker treated
the comparative label `FY2024’te` as an unsupported financial value.

The checker now allows an explicit FY year label only when the same line cites
a non-omitted report excerpt containing that year as a standalone token. This
is a lexical check, not proof of the claim's meaning; Critic still checks the
period and the attached assertion. Bare amounts and other free numeric values
remain prohibited. Metadata binding remains unchanged.

Validation: the exact final failed composition from the UI trace, without
rewriting its prose, passed deterministic rendering and a real configured
Critic call. Result: `intel_comparative_year_regression_20261112.json`.
All 512 Python tests passed; `git diff --check` passed. Tests cover Turkish
apostrophe suffixes, absent years, missing same-line citations, omitted sources,
and monetary values. Two older tests that forbade even a cited literal FY label
now test absent years instead, reflecting this deliberately narrower contract.

No Docker rebuild, deployment, or new end-to-end retrieval was performed.
