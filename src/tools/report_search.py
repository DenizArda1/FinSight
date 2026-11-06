from pathlib import Path
import re
import os

from src.tools.company import resolve_company
from src.utils.utils import load_json, load_yaml
from src.rag.vector_store import get_vector_collection
from src.rag.retrieval import get_latest_report_metadata, search_reports
from src.rag.context import expand_match_context, validate_match_section


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_filing_section(ticker: str, year: int, section: str) -> dict:

    if type(year) is not int or year <= 0:
        raise ValueError("Year must be a positive integer")
    if section not in ("Item 1", "Item 1A", "Item 7"):
        raise ValueError("Section must be Item 1, Item 1A, or Item 7")

    company = resolve_company(ticker)
    processed = Path(os.environ.get("FINSIGHT_PROCESSED_PATH", PROJECT_ROOT / "financial_data" / "processed"))
    summary = load_json(processed / "filing_preparation_summary.json")
    reports = [report for report in summary["reports"]
               if report.get("cik") == company["cik"]
               and report.get("fiscal_year") == year
               and report.get("status") == "prepared"]
    if not reports:
        raise ValueError(f"No prepared filing for {company['ticker']} FY{year}")
    periods = {report["report_date"] for report in reports}
    if len(periods) != 1:
        raise ValueError(f"Multiple reporting periods for {company['ticker']} FY{year}")
    candidates = []
    if len({report["accession_number"] for report in reports}) != len(reports):
        raise ValueError("Duplicate prepared filings; selection is ambiguous")
    for report in reports:
        if not isinstance(report.get("accession_number"), str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", report["accession_number"]):
            raise ValueError("Invalid prepared filing accession number")
        entries = load_json(processed / company["cik"] / "filings" / report["accession_number"] / "sections.json")
        if any(entry.get("section") == section for entry in entries):
            candidates.append(report)
    if not candidates:
        raise ValueError(f"No prepared {section} section for {company['ticker']} FY{year}")
    report = max(candidates, key=lambda item: (item.get("filed", ""), item["accession_number"]))
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
            or filing["form"] not in {"10-K", "10-K/A"}):
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
            "filed": filing.get("filingDate", ""),
            "amendment_note": ("Replacement section from 10-K/A." if filing["form"] == "10-K/A"
                               else "Original section; later amendments without this section do not replace it."),
        },
    }


def search_company_reports(ticker: str, query: str, fiscal_year: int | None = None, top_k: int = 5, section: str | None = None, latest: bool = False) -> dict:
    if type(latest) is not bool:
        raise ValueError("Latest must be a boolean")
    if latest and fiscal_year is not None:
        raise ValueError("Use either latest=True or fiscal_year, not both")

    company = resolve_company(ticker)
    settings_path = PROJECT_ROOT / "configs" / "settings.yaml"
    settings = load_yaml(os.environ.get("FINSIGHT_SETTINGS_PATH", settings_path))

    collection = get_vector_collection(settings["vector_store"])
    selected_report = None
    if latest:
        selected_report = get_latest_report_metadata(collection, company["ticker"])
        fiscal_year = selected_report["fiscal_year"]
    matches = search_reports(
        query=query,
        collection=collection,
        embedding_config=settings["embedding"],
        top_k=top_k,
        ticker=company["ticker"],
        fiscal_year=fiscal_year,
        section=section,
        accession_number=None,
        report_date=selected_report["report_date"] if selected_report else None,
        hybrid=True,
    )
    matches = expand_search_matches(matches, Path(os.environ.get("FINSIGHT_PROCESSED_PATH", PROJECT_ROOT / "financial_data" / "processed")))

    result = {
        "company": company,
        "query": query,
        "fiscal_year": fiscal_year,
        "section": section,
        "matches": matches,
    }
    if latest:
        result.update({"latest": True, "selected_report": selected_report})
    return result


def expand_search_matches(matches, processed_path, padding=400):
    """Attach source-verified surrounding text while preserving ranked chunks."""
    expanded_matches = []
    for match in matches:
        document = load_match_document(match, processed_path)
        metadata = match["metadata"]
        directory = Path(processed_path) / metadata["cik"] / "filings" / metadata["accession_number"]
        sections = load_json(directory / "sections.json")
        validate_match_section(match, document, sections)
        expanded_matches.append(expand_match_context(match, document["text"], padding=padding))
    return expanded_matches


def load_match_document(match, processed_path):

    if not isinstance(match, dict) or not isinstance(match.get("metadata"), dict):
        raise ValueError("Match and metadata must be dictionaries")
    metadata = match["metadata"]
    cik = metadata.get("cik")
    accession = metadata.get("accession_number")
    if not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}", cik):
        raise ValueError("Retrieved CIK must contain exactly ten digits")
    if not isinstance(accession, str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
        raise ValueError("Invalid retrieved accession number")
    for field in ("ticker", "form", "report_date", "source_url"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError(f"Retrieved {field} must be non-empty text")

    year = metadata.get("fiscal_year")
    if type(year) is not int or year <= 0:
        raise ValueError("Retrieved fiscal year must be a positive integer")

    path = Path(processed_path) / cik / "filings" / accession / "text.json"
    document = load_json(path)
    if not isinstance(document, dict):
        raise ValueError("Prepared report must be an object")

    company = document.get("company")
    filing = document.get("filing")
    if not isinstance(company, dict) or not isinstance(filing, dict):
        raise ValueError("Prepared report must contain company and filing objects")

    if (company.get("cik") != cik
            or company.get("ticker") != metadata["ticker"]
            or filing.get("accessionNumber") != accession
            or type(filing.get("fiscal_year")) is not int
            or filing["fiscal_year"] != year
            or filing.get("form") != metadata["form"]
            or filing.get("reportDate") != metadata["report_date"]
            or filing.get("url") != metadata["source_url"]):
        raise ValueError("Prepared report does not match retrieved metadata")
    if not isinstance(document.get("text"), str) or not document["text"].strip():
        raise ValueError("Prepared report text must be non-empty")
    return document
