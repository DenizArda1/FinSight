# Supplemental company and macro sources

The existing MCP server now advertises three additional tools. No new API key is
required. SEC requests continue to use the configured `SEC_USER_AGENT`.

| Tool | Inputs | Coverage |
| --- | --- | --- |
| `search_company_updates` | ticker, English keyword query, form (`10-Q` or `8-K`), limit, top_k | Recent SEC submissions; default four filings, maximum eight. Includes amendments as separate dated evidence. For 8-K, follows up to three HTML EX-99 exhibits per filing. |
| `search_fed_releases` | English keyword query, top_k | Up to eight items from the current Federal Reserve monetary-policy RSS feed, with full article text fetched before retrieval. |
| `get_bls_series` | indicator (`cpi`, `unemployment`, `payrolls`), months | Latest 1–24 available monthly observations from the keyless BLS v1 API. |

## Integration

The filing specialist owns these tools. Planner and specialist instructions route
quarterly filings, recent events and requested macro context to them. Writer/Critic
receive the same source IDs, escaped source text, evidence limits and exact-value
catalog as existing evidence. Fed and BLS links also appear in the source panel and
Markdown export. Annual calculation tools remain unchanged.

Supplemental text uses bounded lexical retrieval with exact character offsets.
It does not change or rebuild the annual Chroma index. English keyword queries are
required for these English corpora; the final answer still follows the user's language.
An unmatched query returns no excerpts rather than unrelated fallback text.

Official responses are cached atomically under `financial_data/supplemental`, with
source URL, retrieval timestamp and text hash. SEC/Fed cache lifetime is six hours;
BLS lifetime is one day. Expired cache entries are refreshed on the next request.
Network failures do not silently reuse stale data. Document failures are reported as
coverage warnings, and successfully retrieved documents remain available.

## Interpretation and limits

- 10-Q documents contain both standalone-quarter and year-to-date values. This
  addition supports source-text research, not a new quarterly calculation engine.
  Do not feed those values into the annual metric pipeline.
- 8-K is an event report, not an annual or quarterly reporting period. Primary
  documents and earnings-release exhibits retain their separate URLs.
- PDF exhibits and non-EX-99 attachments are not parsed in this version.
- Recent SEC submissions and the current Fed RSS feed are bounded discovery windows,
  not historical archives. Historical fiscal-year specialist tasks cannot substitute
  these recent-source tools for the requested period.
- CPI is an index level (1982–84=100), not a percentage inflation rate. Payrolls are
  employment levels in thousands, not month-to-month job additions. Seasonal
  adjustment and BLS footnotes are preserved. Missing `-` observations are reported
  separately; annual-average M13 observations are excluded.
- Fed/BLS evidence supplies economic context, not proof of causation for a company.
  Writers must distinguish company disclosures from broader economic conditions.
- Dates are reported source dates; no page numbers are fabricated for HTML sources.

## Verification (2026-11-12)

Offline tests cover strict tool arguments, form selection, same-directory SEC HTML
exhibit discovery, exact excerpt offsets, BLS units/missing observations, evidence
budgets, source escaping and citation/catalog integration. Existing annual tests remain.

Live checks retrieved Microsoft 10-Q excerpts, 8-K EX-99 earnings-release excerpts,
Federal Reserve excerpts and BLS unemployment observations. One 8-K exhibit index
request timed out; its warning was preserved while other documents succeeded.
All 496 offline tests passed. Actual MCP discovery exposed nine tools, and a BLS
structured-result call passed through the MCP transport.
See `eval/diagnostics/supplemental_sources_20261112.json`. No paid Writer/Critic or
local-model end-to-end evaluation was performed for this source expansion.

Official documentation:
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://www.federalreserve.gov/feeds/feeds.htm
- https://www.bls.gov/developers/api_signature.htm
