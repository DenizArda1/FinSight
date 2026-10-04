"""Run from repository root: python scripts/download_edgar.py."""

import argparse
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from finsight.ingestion.edgar import EdgarClient, write_json


def main():
    parser = argparse.ArgumentParser(description="Download SEC financial data and annual filings")
    parser.add_argument("--tickers", default="NVDA,AAPL,MSFT,AMZN")
    parser.add_argument("--years", type=int, default=5, help="Latest completed annual reporting periods")
    parser.add_argument("--refresh", action="store_true", help="Refresh JSON snapshots; reuse existing HTML")
    args = parser.parse_args()
    if args.years < 1:
        parser.error("--years must be positive")
    env_file = PROJECT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    root = PROJECT / "financial_data" / "raw"
    client = EdgarClient(os.environ.get("SEC_USER_AGENT", ""), root, args.refresh)
    companies = client.fetch("https://www.sec.gov/files/company_tickers.json",
                             root / "company_tickers.json", json_data=True)
    lookup = {company["ticker"].upper(): company for company in companies.values()}
    tickers = list(dict.fromkeys(t.strip().upper() for t in args.tickers.split(",") if t.strip()))
    if not tickers:
        parser.error("At least one ticker is required")
    missing = [ticker for ticker in tickers if ticker not in lookup]
    if missing:
        parser.error(f"Unknown tickers: {', '.join(missing)}")
    manifests = []
    for ticker in tickers:
        print(f"Downloading {ticker}...", flush=True)
        manifest = client.download_company(ticker, lookup[ticker], args.years)
        manifests.append(manifest)
        print(f"{ticker}: CIK {manifest['cik']}, {len(manifest['filings'])} filings", flush=True)
    write_json(root / "download_summary.json", {"companies": manifests})
    print(f"Complete: {client.downloads} downloads, {client.cache_hits} cache hits")


if __name__ == "__main__":
    main()
