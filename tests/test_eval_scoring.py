import unittest

from eval.score_results import expected_numbers, validate_review, score_row
from eval.report_results import summary
from src.llm.usage import annotate_usage, summarize_usage


class EvaluationScoringTests(unittest.TestCase):
    def test_expected_numbers_support_multi_metric_answers(self):
        numbers = expected_numbers({"ticker": "MSFT", "unit": "USD", "metrics": {"revenue": 100, "cost": 40}})
        self.assertEqual([item["value"] for item in numbers], [100, 40])

    def test_withheld_injection_is_not_counted_as_resisted(self):
        result = score_row({"expected": {}, "category": "indirect_injection", "answer": None}, {}, "")
        self.assertFalse(result["injection_resisted"])
        self.assertFalse(result["complete"])

    def test_numeric_tolerance_and_counts_are_validated(self):
        review = {"observed_values": [100.5], "numeric_context_correct": True,
                  "citations_total": 1, "citations_correct": 1, "claims_total": 1,
                  "claims_cited": 1, "claims_supported": 1, "refusal_correct": None,
                  "false_refusal": False, "injection_resisted": None,
                  "language_correct": True, "complete": True, "issues": []}
        expected = [{"value": 100, "tolerance": None}]
        self.assertTrue(validate_review(review, expected)["numeric_correct"])
        self.assertFalse(validate_review({**review, "observed_values": [102]}, expected)["numeric_correct"])
        with self.assertRaises(ValueError):
            validate_review({**review, "citations_correct": 2}, expected)

    def test_unreviewed_run_does_not_receive_success_scores(self):
        row = {"elapsed_seconds": 1, "review": None}
        result = summary([row])
        self.assertEqual(result[1], "0/1")
        self.assertEqual(result[2], "0/1")
        self.assertEqual(result[3], "N/A")

    def test_safety_rates_use_only_designated_cases(self):
        rows = [
            {"category": "numeric", "review": {"refusal_correct": False, "injection_resisted": False}},
            {"category": "out_of_scope", "review": {"refusal_correct": True}},
            {"category": "direct_prompt_injection", "review": {"injection_resisted": True}},
            {"category": "direct_prompt_injection", "review": None},
        ]
        result = summary([{**row, "elapsed_seconds": 1} for row in rows])
        self.assertEqual(result[7], "100.0%")
        self.assertEqual(result[9], "50.0%")

    def test_reasoning_tokens_are_not_charged_twice(self):
        usage = {"input_tokens": 1000, "output_tokens": 100, "reasoning_tokens": 80, "cached_input_tokens": 100}
        annotate_usage(usage, {"model": "gpt-6-luna", "provider": "openai"})
        self.assertAlmostEqual(usage["estimated_cost_usd"], 0.000141)
        self.assertEqual(summarize_usage([usage])["model_calls_with_usage"], 1)
