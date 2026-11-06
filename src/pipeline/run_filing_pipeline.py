import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from src.rag.filings import load_filing, load_latest_filing, select_filings
from src.rag.html_parser import extract_fiscal_year, extract_text
from src.rag.sections import extract_sections
from src.rag.chunking import build_document_chunks
from src.utils.utils import save_json, load_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_PATH = PROJECT_ROOT / "financial_data" / "processed"


def prepare_filing(report, max_chars=1500, overlap=200):
    #Validate all in-memory results before writing any report artifacts
    clean_text = extract_text(report["html"])
    ticker = report["company"]["ticker"]
    if not clean_text.strip():
        raise ValueError(f"No visible report text found for {ticker}")
    try:
        fiscal_year = extract_fiscal_year(report["html"])
    except ValueError:
        if report["filing"]["form"] != "10-K/A" or "original_fiscal_year" not in report:
            raise
        fiscal_year = report["original_fiscal_year"]
    document = {
        "company": report["company"],
        "filing": {**report["filing"], "fiscal_year": fiscal_year},
        "preparation": {
            "schema_version": 2,
            "html_sha256": hashlib.sha256(report["html"].encode("utf-8")).hexdigest(),
            "max_chars": max_chars,
            "overlap": overlap,
        },
        "text": clean_text,
        "sections": extract_sections(clean_text, partial=report["filing"]["form"] == "10-K/A"),
    }
    chunks = build_document_chunks(document, max_chars=max_chars, overlap=overlap)
    if not chunks and report["filing"]["form"] != "10-K/A":
        raise ValueError(f"No text chunks produced for {ticker}")
    document["chunk_count"] = len(chunks)
    return document, chunks


def process_filing(report, max_chars=1500, overlap=200):
    document, chunks = prepare_filing(report, max_chars=max_chars, overlap=overlap)
    directory = (
        PROCESSED_PATH / document["company"]["cik"]
        / "filings" / document["filing"]["accessionNumber"]
    )
    # Each file is replaced atomically; these three writes are not a transaction.
    text_document = {key: value for key, value in document.items() if key != "sections"}
    save_json(text_document, directory / "text.json")
    save_json(document["sections"], directory / "sections.json")
    save_json(chunks, directory / "chunks.json")
    return document


def process_latest_filing(ticker):
    filing = load_latest_filing(ticker)
    return process_filing(filing)


def process_company_filings(ticker, years=5, max_chars=1500, overlap=200):
    selection = select_filings(ticker, years=years)
    results = []
    original_years = {}
    for filing in sorted(selection["filings"], key=lambda item: item["form"] != "10-K"):
        entry = {
            "ticker": selection["company"]["ticker"],
            "cik": selection["company"]["cik"],
            "accession_number": filing.get("accessionNumber"),
            "report_date": filing.get("reportDate"),
            "source_url": filing.get("url"),
            "source_path": filing.get("path"),
            "form": filing["form"], "filed": filing.get("filingDate", ""),
        }
        try:
            report = load_filing(selection["company"], filing)
            if filing["reportDate"] in original_years:
                report["original_fiscal_year"] = original_years[filing["reportDate"]]
            document = process_filing(report, max_chars=max_chars, overlap=overlap)
        except (ValueError, OSError, KeyError) as error:
            entry.update({"status": "failed", "error": str(error)})
        else:
            if filing["form"] == "10-K":
                original_years[filing["reportDate"]] = document["filing"]["fiscal_year"]
            directory = Path(entry["cik"]) / "filings" / entry["accession_number"]
            entry.update({
                "status": "prepared" if document["chunk_count"] else "no_target_sections",
                "fiscal_year": document["filing"]["fiscal_year"],
                "section_count": len(document["sections"]),
                "chunk_count": document["chunk_count"],
                "preparation": document["preparation"],
                "text_path": str(directory / "text.json"),
                "sections_path": str(directory / "sections.json"),
                "sections": [entry["section"] for entry in document["sections"]],
                "chunks_path": str(directory / "chunks.json"),
            })
        results.append(entry)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare local 10-K sections and source-linked chunks")
    parser.add_argument("--tickers", default="NVDA,AAPL,MSFT,AMZN",
                        help="Comma-separated tickers with previously downloaded SEC reports")
    parser.add_argument("--years", type=int, default=5, help="Number of distinct report periods per company")
    parser.add_argument("--max-chars", type=int, default=1500)
    parser.add_argument("--overlap", type=int, default=200)
    args = parser.parse_args(argv)
    tickers = []
    for value in args.tickers.split(","):
        ticker = value.strip().upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    if not tickers:
        parser.error("At least one ticker is required")
    if args.years <= 0:
        parser.error("Years must be a positive integer")
    if args.max_chars <= 0 or not 0 <= args.overlap < args.max_chars:
        parser.error("Require max-chars > 0 and 0 <= overlap < max-chars")

    summary = {
        "schema_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested_tickers": tickers,
        "requested_years": args.years,
        "reports": [],
        "company_errors": [],
        "warnings": [],
    }
    for ticker in tickers:
        try:
            results = process_company_filings(ticker, args.years, args.max_chars, args.overlap)
        except (ValueError, OSError, KeyError) as error:
            summary["company_errors"].append({"ticker": ticker, "error": str(error)})
            print(f"{ticker}: failed: {error}")
            continue
        summary["reports"].extend(results)
        if len(results) < args.years:
            warning = f"{ticker}: requested {args.years} periods; only {len(results)} available"
            summary["warnings"].append(warning)
            print(warning)
        for entry in results:
            if entry["status"] == "prepared":
                detail = f"{entry['chunk_count']} chunks"
            else:
                detail = entry.get("error", "Amendment contains no target narrative sections")
            print(f"{ticker} {entry['report_date']}: {entry['status']} ({detail})")

    summary_path = PROCESSED_PATH / "filing_preparation_summary.json"
    if summary_path.is_file():
        previous = load_json(summary_path)
        summary["reports"].extend(entry for entry in previous.get("reports", []) if entry["ticker"] not in tickers)
        summary["company_errors"].extend(entry for entry in previous.get("company_errors", []) if entry["ticker"] not in tickers)
    summary["prepared_count"] = sum(entry["status"] == "prepared" for entry in summary["reports"])
    summary["failed_count"] = sum(entry["status"] == "failed" for entry in summary["reports"])
    summary_path = PROCESSED_PATH / "filing_preparation_summary.json"
    save_json(summary, summary_path)
    print(f"Preparation manifest: {summary_path}")
    if summary["failed_count"] or summary["company_errors"]:
        parser.exit(1, "Some reports could not be prepared; see the preparation manifest.\n")
    return summary


if __name__ == "__main__":
    main()
