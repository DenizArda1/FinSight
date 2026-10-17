from pathlib import Path

from src.utils.utils import load_json


def resolve_company(ticker: str) -> dict[str, str]:
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("Ticker must be a non-empty string")

    ticker = ticker.strip().upper()

    project_root = Path(__file__).resolve().parents[2]
    companies = load_json(
        project_root / "financial_data" / "raw" / "company_tickers.json"
    )

    for company in companies.values():
        if company["ticker"] == ticker:
            return {
                "ticker": company["ticker"],
                "name": company["title"],
                "cik": str(company["cik_str"]).zfill(10),
            }

    raise ValueError(f"Unknown ticker: {ticker}")
