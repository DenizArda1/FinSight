"""Download official SEC data with sequential requests and verified disk cache."""

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def filing_rows(columns):
    """SEC recent and historical files both contain column-oriented arrays."""
    keys = ("accessionNumber", "form", "filingDate", "reportDate", "primaryDocument")
    count = len(columns.get("accessionNumber", []))
    for index in range(count):
        yield {key: columns.get(key, [""] * count)[index] for key in keys}


def select_filings(rows, years):
    """Select latest N annual reporting periods, including associated amendments."""
    if years < 1:
        raise ValueError("years must be positive")
    unique = {row["accessionNumber"]: row for row in rows}
    periods = sorted({row["reportDate"] for row in unique.values()
                      if row["form"] == "10-K" and row["reportDate"]}, reverse=True)[:years]
    return sorted([row for row in unique.values()
                   if row["form"] in {"10-K", "10-K/A"} and row["reportDate"] in periods],
                  key=lambda row: (row["reportDate"], row["filingDate"]), reverse=True)


class EdgarClient:
    def __init__(self, user_agent, root, refresh=False):
        if "@" not in user_agent or "example.com" in user_agent:
            raise ValueError("Set SEC_USER_AGENT to an application name and real contact email")
        self.user_agent = user_agent
        self.root = Path(root)
        self.refresh = refresh
        self.last_request = 0.0
        self.downloads = 0
        self.cache_hits = 0

    def fetch(self, url, path, *, json_data=False, mutable=True):
        path = Path(path)
        metadata_path = path.with_suffix(path.suffix + ".meta.json")
        if path.exists() and metadata_path.exists() and not (self.refresh and mutable):
            content = path.read_bytes()
            metadata = json.loads(metadata_path.read_text())
            if metadata["url"] == url and metadata["sha256"] == hashlib.sha256(content).hexdigest():
                self.cache_hits += 1
                return json.loads(content) if json_data else content
        for attempt in range(4):
            time.sleep(max(0, 0.25 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                request = Request(url, headers={"User-Agent": self.user_agent,
                                               "Accept-Encoding": "identity"})
                with urlopen(request, timeout=60) as response:
                    content = response.read()
                    content_type = response.headers.get("Content-Type", "")
                if not content:
                    raise ValueError(f"Empty SEC response: {url}")
                parsed = json.loads(content) if json_data else content
                if not json_data and b"<html" not in content.lower() and b"<xhtml" not in content.lower():
                    raise ValueError(f"Expected HTML filing: {url}")
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_bytes(content)
                temporary.replace(path)
                write_json(metadata_path, {
                    "url": url, "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content), "content_type": content_type,
                })
                self.downloads += 1
                return parsed
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == 3:
                    raise
                retry_after = error.headers.get("Retry-After", "")
                time.sleep(min(60, float(retry_after)) if retry_after.isdigit() else 2 ** (attempt + 1))
            except (URLError, TimeoutError):
                if attempt == 3:
                    raise
                time.sleep(2 ** (attempt + 1))

    def download_company(self, ticker, company, years):
        cik = str(company["cik_str"]).zfill(10)
        directory = self.root / cik
        submissions = self.fetch(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            directory / "submissions.json", json_data=True)
        facts = self.fetch(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            directory / "companyfacts.json", json_data=True)
        if int(submissions["cik"]) != int(cik) or int(facts["cik"]) != int(cik):
            raise ValueError(f"SEC company identity mismatch: {ticker}")
        rows = list(filing_rows(submissions["filings"]["recent"]))
        histories = sorted(submissions["filings"].get("files", []),
                           key=lambda item: item["filingTo"], reverse=True)
        for history in histories:
            selected = select_filings(rows, years)
            originals = [row for row in selected if row["form"] == "10-K"]
            # Load overlapping history too, so older originals/amendments aren't missed.
            if len({row["reportDate"] for row in originals}) >= years:
                oldest_date = min(row["filingDate"] for row in originals)
                if history["filingTo"] < oldest_date:
                    break
            name = history["name"]
            if Path(name).name != name:
                raise ValueError("Invalid SEC history filename")
            columns = self.fetch(f"https://data.sec.gov/submissions/{quote(name)}",
                                 directory / "history" / name, json_data=True)
            rows.extend(filing_rows(columns))
        selected = select_filings(rows, years)
        if len({row["reportDate"] for row in selected if row["form"] == "10-K"}) < years:
            raise ValueError(f"Fewer than {years} annual periods available: {ticker}")
        records = []
        for row in selected:
            accession = row["accessionNumber"]
            document = row["primaryDocument"]
            if not document or Path(document).name != document:
                raise ValueError(f"Invalid primary document: {accession}")
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                   f"{accession.replace('-', '')}/{quote(document)}")
            destination = directory / "filings" / accession / document
            self.fetch(url, destination, mutable=False)
            records.append({**row, "url": url, "path": str(destination.relative_to(self.root))})
        manifest = {"ticker": ticker, "cik": cik, "name": submissions["name"],
                    "requested_periods": years, "filings": records,
                    "manifest_generated_at": datetime.now(timezone.utc).isoformat()}
        write_json(directory / "manifest.json", manifest)
        return manifest
