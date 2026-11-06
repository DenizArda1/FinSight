from pathlib import Path

from src.tools.company import resolve_company
from src.utils.utils import load_json


def select_filings(ticker, years=5):
    # Keep originals and all amendments for the latest reporting periods.
    if type(years) is not int or years <= 0:
        raise ValueError("Years must be a positive integer")
    company = resolve_company(ticker)
    project_root = Path(__file__).resolve().parents[2]
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
    amendments = [filing for filing in manifest["filings"]
                  if filing["form"] == "10-K/A" and filing["reportDate"] in report_dates]
    return {"company": company, "filings": sorted(selected + amendments,
            key=lambda filing: (filing["reportDate"], filing["filingDate"], filing.get("accessionNumber", "")), reverse=True)}


def load_filing(company, filing):
    project_root = Path(__file__).resolve().parents[2]
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
    original = next(filing for filing in selection["filings"] if filing["form"] == "10-K")
    return load_filing(selection["company"], original)
