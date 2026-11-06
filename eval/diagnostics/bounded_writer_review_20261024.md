# Bounded evidence bilingual replay — 2026-10-24

Both languages produced answers when given identical short evidence. Independent
review still found semantic errors that Critic approved. This experiment does not
establish that reducing context solves grounding or language reliability.

## Setup

The production Writer and Critic received the same recorded NVIDIA FY2026 Item 1A
chunk (`item_1a:82`), its metadata and 2221 characters of verified expanded context.
There were no new Planner, MCP, retrieval or embedding calls. The diagnostic runner
retains the shared two-revision budget. Production code and model settings were
unchanged. Source identity, section bounds and local text were verified before use.

Only the question language differs between the paired inputs; the evidence and
catalog are identical. The initial prompt lengths are 10044 and 10071 characters.
These are character counts, not token counts.

| Language | Application result | Seconds | Writer attempts | Critic calls |
| --- | --- | ---: | ---: | ---: |
| English | Accepted | 63.8 | 2 | 1 |
| Turkish | Accepted | 33.7 | 1 | 1 |

Total Writer/Critic time was 97.5 seconds. Comparing this directly with the full
pipeline's 593.6 seconds would be misleading: Planner, retrieval and specialist
calls are skipped, and the selected evidence differs from those earlier runs.

## Independent review

### English case

The first response was in Turkish despite the English question. It included the
product identifier `H20`, so the numeric-prose guard rejected it before semantic
review. The repair responded in English. This language drift under short context
means the previous language failure cannot be attributed solely to input length.

The main demand and competitive-disadvantage claims are supported. The final
bullet, however, compresses two source statements into relationship harm caused
by complex compliance requirements and diversion risks. The source distinguishes
compliance burdens from harm caused by **reports of diversion**, including reports
that are unsubstantiated or untrue. That distinction should be preserved.
Individual bullets also lack inline citations, although a single source and its
metadata card are cited elsewhere. Critic approved the answer; independent review
requests semantic and attribution revisions.

### Turkish case

The first response used Turkish and was accepted without repair. Its core claims
about lower demand and harm to market position are supported, but two details are
not faithful to the excerpt:

- “Yerel üreticiler” adds a location relationship not established by the source's
  reference to foreign competitors.
- The final sentence says the situation increases the risk of new restrictions
  being imposed as products launch. The source says export controls increase the
  **risk of investing**, because restrictions may apply by the time a product is
  ready for market. The answer changes this causal relationship.

Critic marked all checks true. This is a semantic false acceptance in the replay,
not a clean quality pass.

## Implications and next steps

Bound the evidence sent to Writer and Critic in the application; preserve the
full-section tool and source offsets, and avoid silently truncating cited text.
Evaluate condition/consequence preservation and language checks with both faithful
and altered claims before changing release criteria. The rule that rejects `H20`
also needs separate consideration: product identifiers are not financial amounts.

These are two development observations with one selected excerpt, not a broad
benchmark or proof of the cause of prior failures. The diagnostic runner is not
an end-to-end MCP test.

See the [structured review](bounded_writer_review_20261024.json),
[raw replay](../results/bounded_writer_replay_20261024T150049_243003Z_ffb91551.json),
and [reproducible runner](run_bounded_writer_replay.py).

Run from the project root with:

```sh
.venv/bin/python -m eval.diagnostics.run_bounded_writer_replay
```
