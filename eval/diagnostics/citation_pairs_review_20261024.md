# Critic citation-pair experiment — 2026-10-24

Critic accepted all four candidates, including both deliberately wrong citations.
It failed to distinguish the two citation swaps in this controlled development
experiment. This is not a model-wide accuracy estimate.

## Controls

The question, evidence, source IDs, model settings and empty fact selection were
identical. Within each pair only the inline citation number changed. All four
drafts passed deterministic schema/rendering/citation-range checks. Expected
labels were recorded separately and were not sent to the model.

The production Critic ran directly against replayed tool evidence. There were no
new Planner, Writer, MCP or embedding calls. Source text and offsets were checked
against local files before the experiment. Production code was unchanged.

## Results

| Claim | Citation | Expected support | Critic decision | Review |
| --- | --- | --- | --- | --- |
| Export regulations may affect shipping/services | Source 4 | Supported | Accepted | Correct acceptance |
| Same claim | Source 1 | Not established by this source | Accepted | False acceptance |
| Additional controls may hinder timely R&D roadmap execution | Source 3 | Supported | Accepted | Correct acceptance |
| Same claim | Source 4 | Not established by this source | Accepted | False acceptance |

Two of two correct citations were accepted. Zero of two wrong citations were
rejected. There were no execution or verdict-format errors. Total Critic time was
107.5 seconds. Every verdict marked evidence support, language and completeness
true, with an empty issues list.

Source 1 is a broad regulatory-risk statement. Source 4 contains the explicit
shipping/services mechanism, and Source 3 contains the R&D-roadmap mechanism.
The existence of the claim's support elsewhere in the evidence set does not make
the deliberately wrong citation valid.

## Interpretation and next step

This reproduces the citation-grounding weakness without Writer variability or a
multi-claim answer. One hypothesis is that providing all sources lets Critic rely
on support outside the cited source, but the experiment does not reveal the
model's internal reasoning.

Repeat the same pairs with only the cited source available to the semantic check,
preserving its original ID. Measure both wrong-citation rejection and correct-
citation acceptance before integrating per-claim verification. This experiment
alone does not justify a broad reliability claim or a production verification
change.

See the [structured review](citation_pairs_review_20261024.json),
[raw results](../results/citation_pairs_20261024T181149_928039Z_0eb243ec.json), and
[reproducible runner](run_citation_pairs.py).

```sh
.venv/bin/python -m eval.diagnostics.run_citation_pairs
```
