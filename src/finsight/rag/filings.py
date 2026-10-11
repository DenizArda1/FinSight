from pathlib import Path

from src.finsight.tools.company import resolve_company
from src.finsight.utils.utils import load_json


def select_filings(ticker, years=5):
    #Select one original 10-K per report date, newest periods first
    if type(years) is not int or years <= 0:
        raise ValueError("Years must be a positive integer")
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

    selected = []
    report_dates = set()
    for filing in sorted_reports:
        if filing["reportDate"] not in report_dates:
            selected.append(filing)
            report_dates.add(filing["reportDate"])
        if len(selected) == years:
            break
    return {"company": company, "filings": selected}


def load_filing(company, filing):
    project_root = Path(__file__).resolve().parents[3]
    raw_path = project_root / "financial_data" / "raw"
    file_path = raw_path / filing["path"]
    html = file_path.read_text(encoding="utf-8")
    
    return {
        "company": company,
        "filing": filing,
        "html": html
    }


def load_latest_filing(ticker):
    selection = select_filings(ticker, years=1)
    return load_filing(selection["company"], selection["filings"][0])
