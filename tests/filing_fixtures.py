"""Small reports with enough narrative content to distinguish them from a TOC."""

REPORT_TEXT = (
    "Item 1. Business\n"
    + "Our company develops products for its customers. " * 8
    + "\nItem 1A. Risk Factors\n"
    + "Changes in demand and competition can affect our business. " * 8
    + "\nItem 1B. Unresolved Staff Comments\nNone.\n"
    + "Item 7. Management’s Discussion and Analysis\n"
    + "Revenue increased following the release of new products. " * 8
    + "\nItem 7A. Quantitative and Qualitative Disclosures About Market Risk\n"
    + "Excluded market risk content.\nItem 8. Financial Statements\nExcluded statements."
).replace(" \n", "\n")
FISCAL_YEAR_HTML = '<ix:header><ix:nonnumeric name="dei:DocumentFiscalYearFocus">2025</ix:nonnumeric></ix:header>'


def make_report():
    return {
        "company": {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193"},
        "filing": {
            "accessionNumber": "test-accession", "form": "10-K",
            "reportDate": "2025-09-27", "filingDate": "2025-10-31",
            "url": "https://example.invalid/report", "path": "test/report.htm",
        },
        "html": FISCAL_YEAR_HTML + "<div>" + REPORT_TEXT.replace("\n", "</div><div>") + "</div>",
    }
