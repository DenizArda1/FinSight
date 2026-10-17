import unittest

from src.data.contracts import validate_calculations, validate_selection


class ContractTests(unittest.TestCase):
    def test_valid_selection_is_accepted(self):
        selection = {
            "forms": ["10-K", "10-K/A"],
            "within_tag": "latest_filed",
            "across_tags": "latest_filed_then_priority",
            "period_fields": ["start", "end"],
            "duration_days": {"min": 350, "max": 380},
        }
        validate_selection(selection)
    
    def test_oldest_filed_is_rejected(self):
        selection = {
            "forms": ["10-K", "10-K/A"],
            "within_tag": "oldest_filed",
            "across_tags": "latest_filed_then_priority",
            "period_fields": ["start", "end"],
            "duration_days": {"min": 350, "max": 380},
        }
        with self.assertRaisesRegex(ValueError, "Unsupported within_tag policy"):
            validate_selection(selection)
    
    def test_invalid_period_fields_are_rejected(self):
        selection = {
            "forms": ["10-K", "10-K/A"],
            "within_tag": "latest_filed",
            "across_tags": "latest_filed_then_priority",
            "period_fields": ["fy"],
            "duration_days": {"min": 350, "max": 380},
        }
        with self.assertRaisesRegex(ValueError, "Unsupported period_fields"):
            validate_selection(selection)

    def test_invalid_across_tags_is_rejected(self):
        selection = {
            "forms": ["10-K", "10-K/A"],
            "within_tag": "latest_filed",
            "across_tags": "last_available",
            "period_fields": ["start", "end"],
            "duration_days": {"min": 350, "max": 380},
        }
        with self.assertRaisesRegex(ValueError, "Unsupported across_tags policy"):
            validate_selection(selection)
    
    def test_reversed_duration_is_rejected(self):
        selection = {
            "forms": ["10-K", "10-K/A"],
            "within_tag": "latest_filed",
            "across_tags": "latest_filed_then_priority",
            "period_fields": ["start", "end"],
            "duration_days": {"min": 380, "max": 350},
        }
        with self.assertRaisesRegex(ValueError, "Maximum duration must not be less than minimum"):
            validate_selection(selection)
    
    def test_non_integer_duration_is_rejected(self):
        selection = {
            "forms": ["10-K", "10-K/A"],
            "within_tag": "latest_filed",
            "across_tags": "latest_filed_then_priority",
            "period_fields": ["start", "end"],
            "duration_days": {"min": "350", "max": 380},
        }
        with self.assertRaisesRegex(ValueError, "Duration bounds must be integers"):
            validate_selection(selection)


    def test_empty_forms_are_rejected(self):
        selection = {
            "forms": [],
            "within_tag": "latest_filed",
            "across_tags": "latest_filed_then_priority",
            "period_fields": ["start", "end"],
            "duration_days": {"min": 350, "max": 380},
        }
        with self.assertRaisesRegex(ValueError, "Forms must be a non-empty list"):
            validate_selection(selection)

    def test_unsupported_form_is_rejected(self):
        selection = {
            "forms": ["10-Q"],
            "within_tag": "latest_filed",
            "across_tags": "latest_filed_then_priority",
            "period_fields": ["start", "end"],
            "duration_days": {"min": 350, "max": 380},
        }
        with self.assertRaisesRegex(ValueError, "Unsupported filing form"):
            validate_selection(selection)


class CalculationContractTests(unittest.TestCase):
    def setUp(self):
        self.metrics = {"revenue": {}, "net_income": {}}
        self.definition = {
            "function": "calculate_margin",
            "inputs": ["net_income", "revenue"],
            "period_mode": "same_period",
            "unit": "ratio",
        }

    def test_valid_calculations_are_accepted(self):
        calculations = {
            "net_margin": self.definition,
            "revenue_growth": {
                "function": "calculate_growth",
                "inputs": ["revenue"],
                "period_mode": "consecutive_periods",
                "unit": "ratio",
            },
            "revenue_cagr": {
                "function": "calculate_cagr",
                "inputs": ["revenue"],
                "period_mode": "full_range",
                "unit": "ratio",
            },
        }
        validate_calculations(calculations, self.metrics)

    def test_invalid_calculations_container_is_rejected(self):
        for calculations in ({}, [], None):
            with self.subTest(calculations=calculations):
                with self.assertRaisesRegex(ValueError, "non-empty dictionary"):
                    validate_calculations(calculations, self.metrics)

    def test_non_dictionary_definition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Definition must be a dictionary for net_margin"):
            validate_calculations({"net_margin": None}, self.metrics)

    def test_invalid_definitions_are_rejected(self):
        cases = [
            ("function", "unknown", "Unsupported function"),
            ("function", [], "Unsupported function"),
            ("period_mode", "full_range", "Unsupported period_mode"),
            ("inputs", "revenue", "Inputs must be a list"),
            ("inputs", ["revenue"], "Unexpected input count"),
            ("inputs", ["unknown", "revenue"], "Unknown input metric"),
            ("inputs", [[], "revenue"], "Unknown input metric"),
            ("inputs", ["revenue", "revenue"], "Duplicate input metrics"),
            ("unit", "USD", "Unsupported unit"),
        ]
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                definition = {**self.definition, field: value}
                with self.assertRaisesRegex(ValueError, f"{message} for net_margin"):
                    validate_calculations({"net_margin": definition}, self.metrics)


if __name__ == "__main__":
    unittest.main()
