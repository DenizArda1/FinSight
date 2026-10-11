# FinSight

FinSight prepares source-linked SEC data for financial tools and report retrieval.
The numerical and narrative data paths are separate: calculations use XBRL facts;
report retrieval uses selected sections of 10-K HTML filings.

## Current stage

Pre-embedding preparation is complete for the locally downloaded reports:

| Company | Fiscal years | Reports | Sections | Chunks |
| --- | --- | ---: | ---: | ---: |
| NVIDIA | 2022–2026 | 5 | 15 | 854 |
| Apple | 2021–2025 | 5 | 15 | 450 |
| Microsoft | 2022–2026 | 5 | 15 | 844 |
| Amazon | 2021–2025 | 5 | 15 | 554 |
| Total | | 20 | 60 | 2,702 |

These counts describe the current local dataset, not a live SEC synchronization.
Fiscal years come from each report's `dei:DocumentFiscalYearFocus`, not its filing
date. Companies have different fiscal calendars and latest available periods.

The numerical path currently provides revenue, net income and operating income,
plus net margin, operating margin, revenue growth and revenue CAGR. Metric
selection and calculation rules live in `configs/metrics.yaml`. Company lookup,
metric retrieval and annual comparisons are available in `src/finsight/tools`.

Next: connect BGE-M3, validate document/query embeddings, build a vector index,
then add retrieval. Agent orchestration, MCP integration and answer verification
remain later stages. Installing a model does not build the index automatically.

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `src/finsight/ingestion/edgar.py` | Download and cache SEC source data |
| `src/finsight/data/explore_facts.py` | Extract annual XBRL metric records |
| `src/finsight/metrics/calculations.py` | Numerical formulas |
| `src/finsight/pipeline/run_metric_pipeline.py` | Coordinate metric calculations |
| `src/finsight/rag/filings.py` | Select report periods and load local HTML |
| `src/finsight/rag/html_parser.py` | Clean HTML and read the declared fiscal year |
| `src/finsight/rag/sections.py` | Locate Business, Risk Factors and MD&A |
| `src/finsight/rag/chunking.py` | Split each section and attach source metadata |
| `src/finsight/pipeline/run_filing_pipeline.py` | Validate, save and log report preparation |
| `src/finsight/utils/utils.py` | Shared JSON/YAML file operations |

## Prepare reports

Run commands from the repository root. Existing local SEC downloads are required;
this command does not make network requests or require the embedding model.

```bash
.venv/bin/python -m src.finsight.pipeline.run_filing_pipeline \
  --tickers NVDA,AAPL,MSFT,AMZN --years 5
```

For one company and its latest report:

```bash
.venv/bin/python -m src.finsight.pipeline.run_filing_pipeline --tickers AAPL --years 1
```

Preparation follows this sequence:

1. Select up to the requested number of distinct report dates from each raw manifest.
2. Clean HTML, reject empty visible text and read the declared fiscal year.
3. Extract Item 1 (Business), Item 1A (Risk Factors) and Item 7 (MD&A).
4. Split each section independently using `RecursiveCharacterTextSplitter`.
5. Validate source offsets and create source-linked chunks before writing files.
6. Save report artifacts and a manifest recording successful and failed reports.

Defaults are 1,500 **characters** per chunk and up to 200 characters of overlap;
these are not token counts or a guarantee of exactly 200 overlapping characters.
Use `--max-chars` and `--overlap` to change them. Token limits and retrieval quality
will be checked when connecting the embedding model.

## Outputs and the embedding handoff

```text
financial_data/
  raw/{cik}/
    manifest.json
    companyfacts.json
    filings/{accession}/{primary_document}.htm
  processed/
    filing_preparation_summary.json
    {cik}/
      ... metric JSON files ...
      filings/{accession}/
        text.json
        sections.json
        chunks.json
```

- `text.json`: cleaned full report, company, filing, source hash and preparation settings.
- `sections.json`: three section texts, titles and absolute source spans.
- `chunks.json`: chunk IDs, texts and flat metadata suitable for later filtering.
- `filing_preparation_summary.json`: requested scope, output paths, counts, warnings and failures.

Chunk metadata includes ticker, CIK, accession, form, fiscal year, report date,
section, title, SEC URL, section boundaries and chunk boundaries. Offsets refer
to the cleaned text in `text.json`; they are not HTML byte offsets. Chunk IDs are
`{accession}:item_{number}:{index}` and remain stable for unchanged input/settings.

The preparation manifest is replaced on each run and describes only that run's
requested scope. Future embedding code should consume only its `prepared` entries,
not glob every `chunks.json` under the data directory. A failed rerun can leave
older artifacts on disk; they must not be treated as newly validated output.
Changed input or chunk settings require replacing that report's indexed chunks,
including removal of obsolete IDs. Indexing and queries must use the same
embedding model and compatible settings.

## Failure handling and limits

- Missing or ambiguous sections and fiscal years fail that report explicitly.
- A report failure is logged while other reports continue. The command exits with
  status 1 after saving the manifest if any report or company failed.
- Fewer local report periods than requested produce a warning; missing periods
  are not downloaded automatically.
- Narrative selection currently uses original `10-K` reports. It does not merge
  `10-K/A` amendments. Numeric fact selection has its own rules in `metrics.yaml`.
- Heading detection requires an item number and its title. Short TOC spans are
  discarded using a 200-character minimum body heuristic. This was verified on
  the current 20 reports; new layouts may need parser extensions.
- HTML cleaning removes scripts, styles, headers, the `hidden` attribute and inline
  `display:none`. It does not evaluate stylesheets or reconstruct merged table cells.
  Financial calculations continue to use XBRL facts rather than parsed HTML tables.
- Each JSON file is replaced atomically, but the three report files are not one
  transaction. Preparation is validated before writing; interrupted writes may
  require rerunning the command before indexing.
- Raw, processed and indexed data directories are excluded from Git. Source reports
  are retained so outputs can be rebuilt and citations traced back to the SEC.

## Validation

```bash
.venv/bin/python -m unittest discover -s tests
```

Tests cover financial calculations and tools, HTML cleanup, fiscal-year extraction,
report selection, TOC/page-header handling, section boundaries, chunk provenance,
and preparation failures. The current 20-report output was also checked for
unique chunk IDs, matching source slices and section-contained chunk boundaries.
