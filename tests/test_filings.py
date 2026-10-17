import unittest
from pathlib import Path
from unittest.mock import patch

from src.rag.filings import load_latest_filing, select_filings


class FilingTests(unittest.TestCase):
    def setUp(self):
        self.company = {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193"}

    def test_multiple_periods_are_selected_without_duplicate_report_dates(self):
        recent = {"form": "10-K", "reportDate": "2025-09-27", "filingDate": "2025-10-31"}
        earlier = {**recent, "filingDate": "2025-10-01"}
        older = {**recent, "reportDate": "2024-09-28"}
        oldest = {**recent, "reportDate": "2023-09-30"}
        with patch("src.rag.filings.resolve_company", return_value=self.company), patch(
            "src.rag.filings.load_json", return_value={"filings": [earlier, oldest, older, recent]}
        ):
            result = select_filings("AAPL", years=2)
        self.assertEqual(result["filings"], [recent, older])

    def test_invalid_period_count_is_rejected(self):
        for years in (0, -1, True, 1.5):
            with self.subTest(years=years), self.assertRaisesRegex(ValueError, "positive integer"):
                select_filings("AAPL", years=years)

    def test_latest_10_k_uses_report_date_then_filing_date(self):
        older_period = {
            "form": "10-K", "reportDate": "2024-09-28", "filingDate": "2026-01-01",
            "path": "0000320193/filings/old/report.htm",
        }
        latest = {
            "form": "10-K", "reportDate": "2025-09-27", "filingDate": "2025-10-31",
            "accessionNumber": "latest", "url": "https://example.invalid/latest",
            "path": "0000320193/filings/latest/report.htm",
        }
        earlier_filing = {**latest, "filingDate": "2025-10-01", "path": "earlier.htm"}
        amendment = {**latest, "form": "10-K/A", "filingDate": "2026-02-01"}
        manifest = {"filings": [older_period, amendment, latest, earlier_filing]}

        with patch("src.rag.filings.resolve_company", return_value=self.company), patch(
            "src.rag.filings.load_json", return_value=manifest
        ), patch.object(Path, "read_text", autospec=True, return_value="<p>Report</p>") as read:
            result = load_latest_filing("AAPL")

        self.assertEqual(result["company"], self.company)
        self.assertEqual(result["filing"], latest)
        self.assertEqual(result["html"], "<p>Report</p>")
        self.assertTrue(str(read.call_args.args[0]).endswith(latest["path"]))

    def test_no_10_k_is_rejected_before_reading_html(self):
        for filings in ([], [{"form": "10-Q"}], [{"form": "10-K/A"}]):
            with self.subTest(filings=filings):
                with patch("src.rag.filings.resolve_company", return_value=self.company), patch(
                    "src.rag.filings.load_json", return_value={"filings": filings}
                ), patch.object(Path, "read_text") as read:
                    with self.assertRaisesRegex(ValueError, "No 10-K filings found for AAPL"):
                        load_latest_filing("AAPL")
                read.assert_not_called()

    def test_missing_html_file_is_reported(self):
        filing = {"form": "10-K", "reportDate": "2025-09-27", "filingDate": "2025-10-31", "path": "missing.htm"}
        with patch("src.rag.filings.resolve_company", return_value=self.company), patch(
            "src.rag.filings.load_json", return_value={"filings": [filing]}
        ), patch.object(Path, "read_text", side_effect=FileNotFoundError("Missing report")):
            with self.assertRaises(FileNotFoundError):
                load_latest_filing("AAPL")


if __name__ == "__main__":
    unittest.main()
