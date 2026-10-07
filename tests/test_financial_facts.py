import unittest

from src.finsight.data.explore_facts import (
    filter_annual_records,
    group_records_by_period,
    merge_metric_tags,
    select_latest_by_period,
)


class FinancialFactTests(unittest.TestCase):
    def setUp(self):
        self.selection = {
            "forms": ["10-K", "10-K/A"],
            "duration_days": {"min": 350, "max": 380},
            "period_fields": ["start", "end"],
            "within_tag": "latest_filed",
            "across_tags": "first_available",
        }
        self.annual_record = {
            "form": "10-K",
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

    def test_tag_priority_wins_over_later_filing_in_fallback_tag(self):
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
            "tag": "PrimaryTag", "record": revised,
        })
        self.assertEqual(selected[("2024-01-01", "2024-12-31")], {
            "tag": "FallbackTag", "record": next_year,
        })

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
