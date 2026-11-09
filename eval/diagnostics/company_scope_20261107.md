# Company scope and narrative follow-up — 7 November 2026

The four original companies are demonstration data, not an application allowlist.
The reference PDF describes SEC XBRL and 10-K data, with company names as examples.
Its supported document format is distinct from company identity coverage.

## Implemented

- UI company selection is free text: ticker, exact company name, or SEC CIK.
- Resolver uses the SEC directory, normalizes legal-name suffixes, refuses ambiguous
  names, refreshes unknown directory entries, and supports CIK-based submissions
  lookup for entities not represented in the ticker directory.
- After validating arguments, MCP requests run the shared preparation hook.
  Financial tools download/prepare missing company data; report tools additionally
  prepare sections and embeddings. Identity-only lookup does not ingest reports.
- The existing pipelines remain responsible for extraction, chunking, calculation
  and embedding. Preparation is serialized across threads/processes; print output
  goes to stderr so it cannot corrupt MCP stdio messages.
- Download accepts less than five available annual periods. Financial results
  disclose the available period count. Growth/CAGR do not silently substitute a
  shorter history for the requested source window.
- New-company indexing preserves other companies, reuses matching vectors, checks
  embedding identity, and stages embeddings before publishing index writes.
  Changed text/metadata and stale IDs are checked per company.
- Base-metric and calculation batch entry points discover downloaded manifests
  rather than enumerating four hard-coded companies.
- Writer does not complete cut-off source lists from background knowledge;
  revision guidance explicitly removes or narrows unsupported claims.

## Evidence

- **488 tests passed**, including new-company identity, ambiguity, short history,
  unsupported forms, caching, validation-before-preparation, per-company index
  isolation, embedding failure, and free-text UI input. Diff whitespace check passed.
- **Adobe**: five annual reports downloaded and processed. Actual application
  answer: FY2025 revenue 23,769,000,000 USD, period end 2025-11-28, with tool citation.
  This is an integration smoke result, not an independent audited answer-key label.
- Adobe added **944 chunks**. Original counts remain AAPL 450, MSFT 844, NVDA 854,
  AMZN 554: **2,702 preserved**, **3,646 total**.
- **Oracle**: before the real MCP financial call its manifest did not exist. The
  call automatically downloaded/prepared the company and returned one latest
  annual revenue record. Adobe Item 1 search returned two matches in the same
  MCP integration run. Oracle report embedding is deferred until requested.
- The two previously withheld narrative cases now released source-supported
  prose. Apple lists product groups without inventing the missing service-list
  continuation. Microsoft competition/innovation claims stay within Source 1's
  competition and platform-ecosystem excerpt. These are assistant source reviews,
  not human calibration or a new overall accuracy score.

Records:

- `company_onboarding_20261107.json`: real MCP cold Oracle preparation and Adobe search.
- `adobe_answer_20261107.json`: actual Qwen/Luna application answer and trace.
- `../results/multi_agent_mcp_20261107T163015_475628Z_98f780b1.json`: two narrative reruns.

## Boundaries retained

This does not claim every SEC registrant has compatible financial facts. The
parser/metric contract currently supports **10-K/10-K/A and configured US-GAAP
concepts**. A 20-F-only issuer receives an explicit unsupported-form error;
20-F/40-F parsing and IFRS metric mapping were not silently added. Missing tags
or unparseable sections remain explicit limitations, not fabricated data.

Existing downloaded snapshots are not automatically refreshed on every question;
use the documented refresh command. New-company ingestion requires SEC network
access and a configured contact User-Agent; report indexing needs local embeddings.
First use can be substantially slower. Model-generated claims remain fallible.

Direct Python tools stay local by default; `execute_tool(..., prepare=True)` uses
the application preparation hook. Synthetic evaluation corpus overrides skip
production preparation. Existing in-progress index synchronization must be
completed before adding another company. Full benchmark/human calibration and
the explicit Critic injection-warning requirement remain open.
