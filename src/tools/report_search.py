from pathlib import Path
import re

from src.tools.company import resolve_company
from src.utils.utils import load_json, load_yaml
from src.rag.vector_store import get_vector_collection
from src.rag.retrieval import search_reports


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_filing_section(ticker: str, year: int, section: str) -> dict:

    if type(year) is not int or year <= 0:
        raise ValueError("Year must be a positive integer")
    if section not in ("Item 1", "Item 1A", "Item 7"):
        raise ValueError("Section must be Item 1, Item 1A, or Item 7")
        
    company = resolve_company(ticker)
    processed = PROJECT_ROOT / "financial_data" / "processed"
    summary = load_json(processed / "filing_preparation_summary.json")
    reports = [report for report in summary["reports"]
               if report.get("cik") == company["cik"]
               and report.get("fiscal_year") == year
               and report.get("status") == "prepared"]
    if not reports:
        raise ValueError(f"No prepared filing for {company['ticker']} FY{year}")
    if len(reports) != 1:
        raise ValueError(f"Multiple prepared filings for {company['ticker']} FY{year}; selection is ambiguous")
    report = reports[0]
    accession = report["accession_number"]
    if not isinstance(accession, str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
        raise ValueError("Invalid prepared filing accession number")
    directory = processed / company["cik"] / "filings" / accession
    document = load_json(directory / "text.json")
    filing = document["filing"]
    if (document["company"]["cik"] != company["cik"]
            or document["company"]["ticker"] != company["ticker"]
            or filing["accessionNumber"] != accession
            or filing["fiscal_year"] != year
            or filing["reportDate"] != report["report_date"]
            or filing["url"] != report["source_url"]
            or filing["form"] != "10-K"):
        raise ValueError("Prepared filing metadata does not match the requested report")
    sections = load_json(directory / "sections.json")
    selected = [entry for entry in sections if entry.get("section") == section]
    if len(selected) != 1:
        raise ValueError(f"Expected one prepared {section} section for {company['ticker']} FY{year}")

    entry = selected[0]
    text, start, end = entry["text"], entry["start"], entry["end"]

    if (not isinstance(text, str) or not text.strip()
            or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(document["text"])
            or document["text"][start:end] != text):
        raise ValueError("Prepared section text or offsets are invalid")

    return {
        "company": company, "year": year, "section": section, "text": text,
        "metadata": {
            "ticker": company["ticker"], "cik": company["cik"],
            "fiscal_year": year, "form": filing["form"],
            "accession_number": accession, "report_date": filing["reportDate"],
            "source_url": filing["url"], "section": section,
            "section_title": entry["title"], "start": start, "end": end,
        },
    }


def search_company_reports(ticker: str,query: str,fiscal_year: int | None = None, top_k: int = 5, section: str | None = None) -> dict:

    company = resolve_company(ticker)
    project_root = Path(__file__).resolve().parents[2]
    settings_path = project_root / "configs" / "settings.yaml"
    settings = load_yaml(settings_path)

    collection = get_vector_collection(settings["vector_store"])
    matches = search_reports(
        query=query,
        collection=collection,
        embedding_config=settings["embedding"],
        top_k=top_k,
        ticker=company["ticker"],
        fiscal_year=fiscal_year,
        section=section,
    )

    return {
        "company": company,
        "query": query,
        "fiscal_year": fiscal_year,
        "section": section,
        "matches": matches,
    }
