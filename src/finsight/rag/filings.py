from pathlib import Path

from src.finsight.tools.company import resolve_company
from src.finsight.utils.utils import load_json


def load_latest_filing(ticker):
    company = resolve_company(ticker)
    project_root = Path(__file__).resolve().parents[3]
    raw_path = project_root / "financial_data" / "raw"
    manifest = load_json(raw_path / company["cik"] / "manifest.json")

    report_10_k = []
    for filing in manifest["filings"]:
        if filing["form"] == "10-K":
            report_10_k.append(filing)

    if not report_10_k:
        raise ValueError(f"No 10-K filings found for {company['ticker']}")
    
    sorted_reports = sorted(
        report_10_k,
        key=lambda filing: (filing["reportDate"], filing["filingDate"]),
        reverse=True,
    )

    latest_filing = sorted_reports[0]
    file_path = raw_path / latest_filing["path"]
    html = file_path.read_text(encoding="utf-8")
    
    return {
        "company": company,
        "filing": latest_filing,
        "html": html
    }
