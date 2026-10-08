import unittest
from unittest.mock import patch

from src.finsight.metrics.calculations import (
    calculate_cagr,
    calculate_margin,
    calculate_growth,
    index_rows_by_period,
) 
from src.finsight.pipeline.run_metric_pipeline import (
    build_cagr_row,
    pair_consecutive_periods,
    process_company_calculations
)

class CalculationTests(unittest.TestCase):
    def test_cagr_uses_number_of_intervals(self):
        result = calculate_cagr(100, 121, 2)
        self.assertAlmostEqual(result, 0.10)

    def test_cagr_rejects_zero_periods(self):
        with self.assertRaises(ValueError):
            calculate_cagr(100, 121, 0)
    
    def test_cagr_handles_decline(self):
        result = calculate_cagr(100, 81, 2)
        self.assertAlmostEqual(result, -0.10)

    def test_margin_allows_negative_income(self):
        result = calculate_margin(-5, 100)
        self.assertAlmostEqual(result, -0.05)
    
    def test_margin_rejects_zero_revenue(self):
        with self.assertRaises(ValueError):
            calculate_margin(25, 0)

    def test_growth_handles_decline(self):
        result = calculate_growth(100, 80)
        self.assertAlmostEqual(result, -0.2)

    def test_growth_rejects_zero_previous_value(self):
        with self.assertRaises(ValueError):
            calculate_growth(0,120)

    def test_duplicate_period_is_rejected(self):
        rows = [
            {"start": "2023-01-01", "end": "2023-12-31"},
            {"start": "2023-01-01", "end": "2023-12-31"},
        ]
        with self.assertRaises(ValueError):
            index_rows_by_period(rows)
    
    def test_missing_year_is_rejected(self):
        rows = [
            {
                "cik": 320193,
                "unit": "USD",
                "start": "2021-01-01",
                "end": "2021-12-31",
            },
            {
                "cik": 320193,
                "unit": "USD",
                "start": "2023-01-01",
                "end": "2023-12-31",
            },
        ]
        with self.assertRaises(ValueError):
            pair_consecutive_periods(rows)

    def test_company_calculations_use_configured_inputs_and_names(self):
        sales_rows = [
            {
                "cik": "0000320193",
                "unit": "USD",
                "start": "2023-01-01",
                "end": "2023-12-31",
                "value": 100,
            },
            {
                "cik": "0000320193",
                "unit": "USD",
                "start": "2024-01-01",
                "end": "2024-12-31",
                "value": 120,
            },
        ]
        profit_rows = [
            {
                "cik": "0000320193",
                "unit": "USD",
                "start": "2023-01-01",
                "end": "2023-12-31",
                "value": 20,
            },
            {
                "cik": "0000320193",
                "unit": "USD",
                "start": "2024-01-01",
                "end": "2024-12-31",
                "value": 30,
            },
        ]
        calculations = {
            "profit_ratio": {
                "function": "calculate_margin",
                "unit": "ratio",
                "inputs": ["profit", "sales"],
                "period_mode": "same_period",
            },
            "sales_growth": {
                "function": "calculate_growth",
                "unit": "ratio",
                "inputs": ["sales"],
                "period_mode": "consecutive_periods",
            },
            "sales_cagr": {
                "function": "calculate_cagr",
                "unit": "ratio",
                "inputs": ["sales"],
                "period_mode": "full_range",
            },
        }
        with patch("src.finsight.pipeline.run_metric_pipeline.load_json") as mock_load, patch(
            "src.finsight.pipeline.run_metric_pipeline.save_json"
        ) as mock_save:
            #The first calculation loads profit, then sales. Later calculations reuse sales.
            mock_load.side_effect = [profit_rows, sales_rows]

            results = process_company_calculations (
                "0000320193", calculations, {"profit": {}, "sales": {}}
            )

        self.assertEqual(set(results), set(calculations))
        self.assertEqual(mock_load.call_count, 2)
        self.assertEqual(mock_load.call_args_list[0].args[0].name, "profit.json")
        self.assertEqual(mock_load.call_args_list[1].args[0].name, "sales.json")

        saved_names = []
        for save_call in mock_save.call_args_list:
            output_path = save_call.args[1]
            saved_names.append(output_path.stem)
        self.assertEqual(saved_names, list(calculations))
        self.assertEqual(len(results["profit_ratio"]), 2)
        self.assertAlmostEqual(results["profit_ratio"][1]["value"], 0.25)
        self.assertAlmostEqual(results["sales_growth"][0]["value"], 0.20)
        self.assertAlmostEqual(results["sales_cagr"][0]["value"], 0.20)
        self.assertEqual(results["profit_ratio"][0]["formula"], "profit / sales")
        self.assertIn("previous_sales", results["sales_growth"][0]["inputs"])
        self.assertIn("start_sales", results["sales_cagr"][0]["inputs"])
        for name, rows in results.items():
            for row in rows:
                self.assertEqual(row["metric"], name)

    def test_invalid_config_is_rejected_before_file_operations(self):
        definition = {
            "function": "calculate_margin",
            "inputs": ["net_income", "revenue"],
            "period_mode": "same_period",
            "unit": "ratio",
        }
        cases = [
            ("function", "unknown", "Unsupported function"),
            ("period_mode", "full_range", "Unsupported period_mode"),
            ("inputs", ["revenue", "revenue"], "Duplicate input metrics"),
            ("inputs", ["unknown", "revenue"], "Unknown input metric"),
        ]
        for field, value, message in cases:
            with self.subTest(field=field):
                calculations = {"net_margin": {**definition, field: value}}
                with patch("src.finsight.pipeline.run_metric_pipeline.load_json") as mock_load, patch(
                    "src.finsight.pipeline.run_metric_pipeline.save_json"
                ) as mock_save:
                    with self.assertRaisesRegex(ValueError, message):
                        process_company_calculations(
                            "0000320193", calculations, {"net_income": {}, "revenue": {}}
                        )
                    mock_load.assert_not_called()
                    mock_save.assert_not_called()

    def test_cagr_row_orders_records_and_preserves_sources(self):
        first_record = {
            "cik": "0000320193", "unit": "USD",
            "start": "2022-01-01", "end": "2022-12-31", "value": 100,
        }
        middle_record = {
            "cik": "0000320193", "unit": "USD",
            "start": "2023-01-01", "end": "2023-12-31", "value": 110,
        }
        last_record = {
            "cik": "0000320193", "unit": "USD",
            "start": "2024-01-01", "end": "2024-12-31", "value": 121,
        }
        result = build_cagr_row([last_record, first_record, middle_record])
        self.assertAlmostEqual(result["value"], 0.10)
        self.assertEqual(result["periods"], 2)
        self.assertEqual(result["inputs"]["start_revenue"], first_record)
        self.assertEqual(result["inputs"]["end_revenue"], last_record)

        with self.assertRaisesRegex(ValueError, "Annual periods are not consecutive"):
            build_cagr_row([first_record, last_record])

if __name__ == "__main__":
    unittest.main()
