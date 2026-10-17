import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from src.ingestion.edgar import EdgarClient, filing_rows, select_filings


class EdgarTests(unittest.TestCase):
    def test_period_selection_includes_amendment_and_deduplicates(self):
        rows = [
            {"accessionNumber": "a", "form": "10-K", "reportDate": "2025-09-27", "filingDate": "2025-10-31"},
            {"accessionNumber": "b", "form": "10-K/A", "reportDate": "2025-09-27", "filingDate": "2026-01-01"},
            {"accessionNumber": "c", "form": "10-K", "reportDate": "2024-09-28", "filingDate": "2024-11-01"},
            {"accessionNumber": "d", "form": "10-Q", "reportDate": "2026-03-31", "filingDate": "2026-05-01"},
        ]
        selected = select_filings(rows + rows, 1)
        self.assertEqual({r["accessionNumber"] for r in selected}, {"a", "b"})

    def test_historical_columns(self):
        rows = list(filing_rows({"accessionNumber": ["a"], "form": ["10-K"]}))
        self.assertEqual(rows[0]["form"], "10-K")
        self.assertEqual(rows[0]["reportDate"], "")

    def test_second_fetch_uses_verified_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            client = EdgarClient("FinSight contact@mydomain.test", directory)
            path = Path(directory) / "facts.json"
            with patch("src.ingestion.edgar.urlopen") as mock:
                response = mock.return_value.__enter__.return_value
                response.read.return_value = b'{"cik": 1}'
                response.headers.get.return_value = "application/json"
                first = client.fetch("https://data.sec.gov/test", path, json_data=True)
                second = client.fetch("https://data.sec.gov/test", path, json_data=True)
                self.assertEqual(first, second)
                self.assertEqual(mock.call_count, 1)
                self.assertEqual(client.cache_hits, 1)
                self.assertIn("sha256", json.loads(path.with_suffix(".json.meta.json").read_text()))

    def test_placeholder_contact_rejected(self):
        with self.assertRaises(ValueError):
            EdgarClient("FinSight your-email@example.com", ".")

    def test_403_is_retried_with_bounded_backoff(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "src.ingestion.edgar.urlopen"
        ) as request, patch("src.ingestion.edgar.time.sleep") as sleep:
            error = HTTPError("https://data.sec.gov/test", 403, "Forbidden", {}, None)
            request.side_effect = error
            client = EdgarClient("FinSight contact@mydomain.test", directory)
            with self.assertRaises(HTTPError):
                client.fetch(error.url, Path(directory) / "facts.json", json_data=True)
            self.assertEqual(request.call_count, 4)
            delays = [call.args[0] for call in sleep.call_args_list]
            for delay in (2, 4, 8):
                self.assertIn(delay, delays)


if __name__ == "__main__":
    unittest.main()
