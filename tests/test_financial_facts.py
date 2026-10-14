import unittest

from src.finsight.data.explore_facts import (
    filter_annual_records,
    group_records_by_period,
    merge_metric_tags,
    select_latest_by_period,
    build_metric_rows,
)


class FinancialFactTests(unittest.TestCase):
    def setUp(self):
        self.selection = {
            "forms": ["10-K", "10-K/A"],
            "duration_days": {"min": 350, "max": 380},
            "period_fields": ["start", "end"],
            "within_tag": "latest_filed",
            "across_tags": "latest_filed_then_priority",
        }
        self.annual_record = {
            "form": "10-K",
            "fp": "FY",
            "start": "2023-01-01",
            "end": "2023-12-31",
            "filed": "2024-02-01",
            "val": 100,
            "accn": "original",
        }

    def test_annual_filter_rejects_quarterly_and_instant_records(self):
        amendment = {**self.annual_record, "form": "10-K/A"}
        wrong_form = {**self.annual_record, "form": "10-Q"}
        short_period = {**self.annual_record, "end": "2023-03-31"}
        long_period = {**self.annual_record, "end": "2024-12-31"}
        instant_record = {"form": "10-K", "end": "2023-12-31", "val": 100}

        records = [
            self.annual_record, amendment, wrong_form,
            short_period, long_period, instant_record,
        ]
        selected = filter_annual_records(records, self.selection)
        self.assertEqual(selected, [self.annual_record, amendment])

    def test_latest_filing_is_selected_for_each_period(self):
        revised = {
            **self.annual_record, "filed": "2025-02-01",
            "val": 105, "accn": "revision",
        }
        next_year = {
            **self.annual_record, "start": "2024-01-01",
            "end": "2024-12-31", "filed": "2025-02-01",
        }
        grouped = group_records_by_period([revised, next_year, self.annual_record])
        selected = select_latest_by_period(grouped)

        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[("2023-01-01", "2023-12-31")], revised)
        self.assertEqual(selected[("2024-01-01", "2024-12-31")], next_year)

    def test_later_filing_wins_over_tag_priority(self):
        revised = {**self.annual_record, "filed": "2025-02-01", "val": 105}
        fallback_record = {**self.annual_record, "filed": "2026-02-01", "val": 999}
        next_year = {
            **self.annual_record, "start": "2024-01-01",
            "end": "2024-12-31", "filed": "2025-02-01", "val": 120,
        }
        facts = {
            "PrimaryTag": {"units": {"USD": [self.annual_record, revised]}},
            "FallbackTag": {"units": {"USD": [fallback_record, next_year]}},
        }
        selected = merge_metric_tags(
            facts, ["PrimaryTag", "FallbackTag"], self.selection, "USD"
        )

        self.assertEqual(selected[("2023-01-01", "2023-12-31")], {
            "tag": "FallbackTag", "record": fallback_record,
        })
        self.assertEqual(selected[("2024-01-01", "2024-12-31")], {
            "tag": "FallbackTag", "record": next_year,
        })

    def test_tag_priority_breaks_same_filed_date_ties(self):
        facts = {
            "PrimaryTag": {"units": {"USD": [self.annual_record]}},
            "FallbackTag": {"units": {"USD": [{**self.annual_record, "val": 999}]}},
        }
        selected = merge_metric_tags(facts, ["PrimaryTag", "FallbackTag"], self.selection, "USD")
        self.assertEqual(selected[("2023-01-01", "2023-12-31")]["tag"], "PrimaryTag")

    def test_annual_duration_with_non_annual_fiscal_period_is_rejected(self):
        for fp in ("Q4", None):
            with self.subTest(fp=fp):
                self.assertEqual(filter_annual_records([{**self.annual_record, "fp": fp}], self.selection), [])

    def test_old_metric_periods_do_not_replace_missing_requested_periods(self):
        periods = {("2023-01-01", "2023-12-31"): {"tag": "GrossProfit", "record": self.annual_record}}
        self.assertEqual(build_metric_rows("1", "gross_profit", periods, "USD", period_ends=["2025-12-31"]), [])

    def test_amendment_is_selected_and_identified(self):
        amended = {**self.annual_record, "form": "10-K/A", "filed": "2024-03-01", "val": 110}
        selected = merge_metric_tags(
            {"Tag": {"units": {"USD": [self.annual_record, amended]}}}, ["Tag"], self.selection, "USD",
        )
        rows = build_metric_rows("1", "revenue", selected, "USD")
        self.assertEqual(rows[0]["value"], 110)
        self.assertTrue(rows[0]["is_amendment"])

    def test_missing_tags_and_unavailable_units_use_fallback(self):
        facts = {
            "WrongUnitTag": {"units": {"EUR": [self.annual_record]}},
            "EmptyTag": {"units": {"USD": []}},
            "FallbackTag": {"units": {"USD": [self.annual_record]}},
        }
        selected = merge_metric_tags(
            facts,
            ["MissingTag", "WrongUnitTag", "EmptyTag", "FallbackTag"],
            self.selection,
            "USD",
        )
        self.assertEqual(selected[("2023-01-01", "2023-12-31")], {
            "tag": "FallbackTag", "record": self.annual_record,
        })


if __name__ == "__main__":
    unittest.main()
