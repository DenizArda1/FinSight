import argparse
from pathlib import Path

from src.finsight.rag.filings import load_latest_filing
from src.finsight.rag.html_parser import extract_text
from src.finsight.rag.chunking import build_document_chunks
from src.finsight.utils.utils import save_json


def process_latest_filing(ticker):
    report = load_latest_filing(ticker)
    clean_text = extract_text(report["html"])
    if not clean_text.strip():
        raise ValueError(f"No visible report text found for {report['company']['ticker']}")

    document = {
        "company": report["company"],
        "filing": report["filing"],
        "text": clean_text,
    }
    chunks = build_document_chunks(document)
    if not chunks:
        raise ValueError(f"No text chunks produced for {report['company']['ticker']}")

    project_root = Path(__file__).resolve().parents[3]
    file_path = (
        project_root
        / "financial_data"
        / "processed"
        / report["company"]["cik"]
        / "filings"
        / report["filing"]["accessionNumber"]
        / "text.json"
    )
    chunks_path = file_path.with_name("chunks.json")
    save_json(document, file_path)
    save_json(chunks, chunks_path)
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Prepare local 10-K text and source-linked chunks"
    )
    parser.add_argument(
        "--tickers", default="NVDA,AAPL,MSFT,AMZN",
        help="Comma-separated tickers with previously downloaded SEC reports",
    )
    args = parser.parse_args(argv)
    tickers = []
    for value in args.tickers.split(","):
        ticker = value.strip().upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    if not tickers:
        parser.error("At least one ticker is required")

    for ticker in tickers:
        try:
            document = process_latest_filing(ticker)
        except (ValueError, OSError) as error:
            parser.exit(1, f"{ticker}: {error}\n")
        print(f"{ticker}: processed 10-K for {document['filing']['reportDate']}")


if __name__ == "__main__":
    main()
