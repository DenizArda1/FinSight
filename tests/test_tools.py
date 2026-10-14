import unittest
from unittest.mock import call, patch

from src.finsight.tools.financial_metrics import compare_metric, index_records_by_end_year


class ToolTests(unittest.TestCase):
    def test_records_are_indexed_by_end_year(self):
        records = [
            {"end": "2025-09-27", "value": 100},
            {"end": "2024-09-28", "value": 90},
        ]

        result = index_records_by_end_year(records)

        self.assertEqual(result[2025], records[0])
        self.assertEqual(result[2024], records[1])

    def test_duplicate_end_year_is_rejected(self):
        records = [
            {"end": "2025-09-27", "value": 100},
            {"end": "2025-06-30", "value": 90},
        ]

        with self.assertRaisesRegex(ValueError, "Year is already in dictionary"):
            index_records_by_end_year(records)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.apple = {
            "company": {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193"},
            "metric": "revenue",
            "records": [
                {"start": "2023-10-01", "end": "2024-09-28", "value": 90, "unit": "USD", "accn": "apple-2024"},
                {"start": "2024-09-29", "end": "2025-09-27", "value": 100, "unit": "USD", "accn": "apple-2025"},
            ],
        }
        self.microsoft = {
            "company": {"ticker": "MSFT", "name": "Microsoft Corp.", "cik": "0000789019"},
            "metric": "revenue",
            "records": [
                {"start": "2023-07-01", "end": "2024-06-30", "value": 180, "unit": "USD", "accn": "microsoft-2024"},
                {"start": "2024-07-01", "end": "2025-06-30", "value": 200, "unit": "USD", "accn": "microsoft-2025"},
                {"start": "2025-07-01", "end": "2026-06-30", "value": 220, "unit": "USD", "accn": "microsoft-2026"},
            ],
        }

    def test_limit_is_applied_after_finding_common_years(self):
        expected_apple = self.apple["records"][1]
        expected_microsoft = self.microsoft["records"][1]

        with patch("src.finsight.tools.financial_metrics.get_metric") as mock_get, patch(
            "src.finsight.tools.financial_metrics.load_yaml", 
            return_value={"calculations": {}}
        ):
            mock_get.side_effect = [self.apple, self.microsoft]
            result = compare_metric(["AAPL", "MSFT"], "revenue", limit=1)

        self.assertEqual(mock_get.call_args_list, [call("AAPL", "revenue"), call("MSFT", "revenue")])
        self.assertEqual(result["common_years"], [2025])
        self.assertEqual(result["comparison_basis"], "period_end_calendar_year")
        self.assertIn("not identical fiscal calendars", result["notes"][0])
        self.assertEqual(result["results"][0]["records"], [expected_apple])
        self.assertEqual(result["results"][1]["records"], [expected_microsoft])
        self.assertEqual(result["results"][0]["company"]["ticker"], "AAPL")

    def test_common_years_include_all_companies_and_are_newest_first(self):
        amazon = {
            "company": {"ticker": "AMZN"},
            "metric": "revenue",
            "records": [
                {"end": "2024-12-31", "value": 300},
                {"end": "2023-12-31", "value": 280},
            ],
        }
        with patch("src.finsight.tools.financial_metrics.get_metric") as mock_get, patch(
            "src.finsight.tools.financial_metrics.load_yaml", 
            return_value={"calculations": {}}
        ):
            mock_get.side_effect = [self.apple, self.microsoft, amazon]
            result = compare_metric(["AAPL", "MSFT", "AMZN"], "revenue")

        self.assertEqual(result["common_years"], [2024])

        for company_result in result["results"]:
            self.assertEqual(len(company_result["records"]), 1)
            self.assertTrue(company_result["records"][0]["end"].startswith("2024"))

    def test_multiple_common_years_are_newest_first(self):
        with patch("src.finsight.tools.financial_metrics.get_metric") as mock_get, patch (
            "src.finsight.tools.financial_metrics.load_yaml", 
            return_value={"calculations": {}}
        ):

            mock_get.side_effect = [self.apple, self.microsoft]
            result = compare_metric(["AAPL", "MSFT"], "revenue")

        self.assertEqual(result["common_years"], [2025, 2024])

        for company_result in result["results"]:
            self.assertTrue(company_result["records"][0]["end"].startswith("2025"))
            self.assertTrue(company_result["records"][1]["end"].startswith("2024"))

    def test_non_overlapping_years_are_rejected(self):
        self.microsoft["records"] = [self.microsoft["records"][2]]
        with patch("src.finsight.tools.financial_metrics.get_metric") as mock_get, patch(
            "src.finsight.tools.financial_metrics.load_yaml", 
            return_value={"calculations": {}}
        ):
            mock_get.side_effect = [self.apple, self.microsoft]
            with self.assertRaisesRegex(ValueError, "No common period end years found"):
                compare_metric(["AAPL", "MSFT"], "revenue")

    def test_full_range_metric_is_rejected(self):
        self.apple["metric"] = "revenue_cagr"
        self.microsoft["metric"] = "revenue_cagr"
        config = {"calculations": {"revenue_cagr": {"period_mode": "full_range"}}}
        with patch("src.finsight.tools.financial_metrics.get_metric") as mock_get, patch (
            "src.finsight.tools.financial_metrics.load_yaml", 
            return_value=config
        ):
            mock_get.side_effect = [self.apple, self.microsoft]
            with self.assertRaisesRegex(ValueError, "Full-range metrics require a separate interval comparison"):
                compare_metric(["AAPL", "MSFT"], "revenue_cagr")


if __name__ == "__main__":
    unittest.main()
