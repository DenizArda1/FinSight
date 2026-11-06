# Report evidence limits — 2026-10-24

Writer and Critic now share a bounded report-evidence view built from the original
tool trace. The single-agent final answer path uses the same policy.

- Maximum report text per source: 6000 characters.
- Maximum report text across sources: 12000 characters.
- Original chunk text and expanded context both count toward the limits.
- Search excerpts have priority over full sections; within each group, original
  retrieval order is preserved. Financial records are unchanged.
- Sources are admitted whole or omitted whole; no partial text or offsets are
  fabricated. Omission markers preserve source IDs and carry a reason and a hash
  of the original result. Omitted sources cannot be cited or selected as facts.
- Writer and Critic recompute the same projection. Changes to omitted raw evidence
  are still detected by its fingerprint. The trace retains the original tool result.

The defaults live in `src/verification/evidence.py`. They are provisional character
budgets for report text, not a tokenizer-based limit for the entire model prompt.
Full-section tools still return complete data. Specialist tool conversations are
not bounded by this change; the policy applies to final-answer evidence preparation.
An explicit request to summarize an oversized full section may require an honest
coverage limitation; no hierarchical section summarizer is introduced here.

## Offline verification

180 tests passed across evidence limits, Writer, Critic, agent verification,
orchestration, single-agent execution, evaluation, filing tools and report context.
New checks cover total/per-source limits, stable IDs, admission priority, original
offsets, forbidden citations, all-omitted limitations, unchanged tool results and
identical Writer/Critic inputs. The diff whitespace check passed.

Rebuilding prompts from the saved NVIDIA bilingual run produced:

| Case | Included report text | Omitted IDs | Initial Writer prompt |
| --- | ---: | --- | ---: |
| English | 11710 characters | 4 | 22836 characters |
| Turkish | 1286 characters | 2 | 8722 characters |

The previous Turkish prompt was 123917 characters; its full-section text is now
replaced by a marked omission. The remaining source is a broad excerpt, so the
Writer must not claim to have reviewed the complete section or invent missing
detail. Better retrieval or explicit limitations may still be necessary.

This validation made **no model calls**. It proves the deterministic projection
and citation rules, not improved answer quality. The next live check should use
the complete MCP path and inspect both coverage and the treatment of omissions.

See the [offline measurement](evidence_limits_20261024.json).
