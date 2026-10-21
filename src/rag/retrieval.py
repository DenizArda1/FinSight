from datetime import date
import re

from src.rag.embeddings import embed_text


def search_reports(query, collection, embedding_config, top_k=5, ticker=None, fiscal_year=None, section=None, accession_number=None):
    if type(top_k) is not int or top_k <= 0:
        raise ValueError("top_k must be a positive integer")
    if ticker is not None:
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("Ticker must be a non-empty string")
        ticker = ticker.strip().upper()
    if fiscal_year is not None:
        if type(fiscal_year) is not int or fiscal_year <= 0:
            raise ValueError("Fiscal year must be a positive integer")
    if section is not None:
        if not isinstance(section, str) or not section.strip():
            raise ValueError("Section must be a non-empty string")
        section = section.strip()
    if accession_number is not None:
        if not isinstance(accession_number, str) or not accession_number.strip():
            raise ValueError("Accession number must be a non-empty string")
    filters = []
    if ticker is not None:
        filters.append({"ticker": ticker})
    if fiscal_year is not None:
        filters.append({"fiscal_year": fiscal_year})
    if section is not None:
        filters.append({"section": section})
    if accession_number is not None:
        filters.append({"accession_number": accession_number})

    if not filters:
        where = None
    elif len(filters) == 1:
        where = filters[0]
    else:
        where = {"$and": filters}

    query_vector = embed_text(query, embedding_config)
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    return format_search_results(results)


def format_search_results(results):
    matches = []
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]
    for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances, strict=True):
        match = {
            "chunk_id": chunk_id,
            "text": text,
            "metadata": metadata,
            "distance": distance,
        }
        matches.append(match)
    return matches


def get_latest_report_metadata(collection, ticker):
    """Select the newest indexed report by period end, before section filtering."""
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("Ticker must be a non-empty string")
    ticker = ticker.strip().upper()
    results = collection.get(
        where={"ticker": ticker},
        include=["metadatas"],
    )
    metadatas = results.get("metadatas")
    if not isinstance(metadatas, list):
        raise ValueError("Indexed report metadata must be a list")
    if not metadatas:
        raise ValueError(f"No indexed reports for {ticker}")

    reports = {}
    for metadata in metadatas:
        if not isinstance(metadata, dict) or metadata.get("ticker") != ticker:
            raise ValueError("Indexed report metadata does not match the requested ticker")

        report_date = metadata.get("report_date")
        if not isinstance(report_date, str):
            raise ValueError("Report date must be an ISO date string")

        try:
            parsed_date = date.fromisoformat(report_date)
        except ValueError as error:
            raise ValueError("Report date must be a valid ISO date") from error
        if parsed_date.isoformat() != report_date:
            raise ValueError("Report date must use YYYY-MM-DD format")

        fiscal_year = metadata.get("fiscal_year")
        if type(fiscal_year) is not int or fiscal_year <= 0:
            raise ValueError("Reported fiscal year must be a positive integer")

        accession = metadata.get("accession_number")
        if not isinstance(accession, str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
            raise ValueError("Indexed report accession number is invalid")
        report = {
            "fiscal_year": fiscal_year, "report_date": report_date,
            "accession_number": accession,
        }
        if accession in reports and reports[accession] != report:
            raise ValueError("Chunks contain conflicting metadata for the same report")
        reports[accession] = report

    latest_date = max(report["report_date"] for report in reports.values())
    latest_reports = [report for report in reports.values() if report["report_date"] == latest_date]
    if len(latest_reports) != 1:
        raise ValueError(f"Multiple indexed reports share the latest period end for {ticker}")
    return latest_reports[0]
