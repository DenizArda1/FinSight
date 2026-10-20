import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from jsonschema import Draft202012Validator

from src.agents.planner import (
    PLANNER_RESPONSE_SCHEMA,
    generate_plan,
    validate_plan,
)


def make_plan(request_type, agents):
    return {
        "request_type": request_type,
        "tasks": [
            {
                "id": f"task_{index}",
                "agent": agent,
                "instruction": "Retrieve Apple's latest annual evidence.",
            }
            for index, agent in enumerate(agents, start=1)
        ],
    }


class PlannerValidationTests(unittest.TestCase):
    def test_schema_is_valid(self):
        Draft202012Validator.check_schema(PLANNER_RESPONSE_SCHEMA)

    def test_accepts_valid_routes_without_mutating_plan(self):
        cases = [
            ("financial", ["financial_data"]),
            ("filing", ["filing_rag"]),
            ("mixed", ["financial_data", "filing_rag"]),
            ("comparison", ["financial_data"]),
            ("comparison", ["filing_rag"]),
            ("comparison", ["financial_data", "filing_rag"]),
            ("out_of_scope", []),
            ("clarification", []),
            ("financial", ["financial_data"] * 6),
        ]
        for request_type, agents in cases:
            with self.subTest(request_type=request_type, agents=agents):
                plan = make_plan(request_type, agents)
                original = deepcopy(plan)
                self.assertIsNone(validate_plan(plan))
                self.assertEqual(plan, original)

    def test_rejects_empty_research_plans(self):
        for request_type in ("financial", "filing", "mixed", "comparison"):
            with self.subTest(request_type=request_type):
                with self.assertRaisesRegex(ValueError, "at least one task"):
                    validate_plan(make_plan(request_type, []))

    def test_rejects_tasks_for_non_research_routes(self):
        for request_type in ("out_of_scope", "clarification"):
            with self.subTest(request_type=request_type):
                with self.assertRaisesRegex(ValueError, "must not contain tasks"):
                    validate_plan(make_plan(request_type, ["financial_data"]))

    def test_rejects_inconsistent_agent_routes(self):
        cases = [
            ("financial", ["filing_rag"]),
            ("financial", ["financial_data", "filing_rag"]),
            ("filing", ["financial_data"]),
            ("filing", ["financial_data", "filing_rag"]),
            ("mixed", ["financial_data"]),
            ("mixed", ["filing_rag"]),
        ]
        for request_type, agents in cases:
            with self.subTest(request_type=request_type, agents=agents):
                with self.assertRaises(ValueError):
                    validate_plan(make_plan(request_type, agents))

    def test_rejects_duplicate_ids(self):
        plan = make_plan("mixed", ["financial_data", "filing_rag"])
        plan["tasks"][1]["id"] = plan["tasks"][0]["id"]
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_plan(plan)

    def test_rejects_blank_fields_and_padded_ids(self):
        for field, value in (
            ("id", " \t"), ("id", " task_1"), ("id", "task_1\n"),
            ("instruction", " \n\t"),
        ):
            with self.subTest(field=field, value=value):
                plan = make_plan("financial", ["financial_data"])
                plan["tasks"][0][field] = value
                with self.assertRaises(ValueError):
                    validate_plan(plan)

    def test_rejects_schema_violations(self):
        extra_root = make_plan("financial", ["financial_data"])
        extra_root["answer"] = "Invented answer"
        extra_task = make_plan("financial", ["financial_data"])
        extra_task["tasks"][0]["tool"] = "unknown"
        missing_instruction = make_plan("financial", ["financial_data"])
        del missing_instruction["tasks"][0]["instruction"]
        non_string_id = make_plan("financial", ["financial_data"])
        non_string_id["tasks"][0]["id"] = True
        for plan in (
            None, [], {}, {"request_type": "financial", "tasks": {}},
            make_plan("unknown", []), make_plan("financial", ["writer"]),
            make_plan("financial", ["financial_data"] * 7),
            extra_root, extra_task, missing_instruction, non_string_id,
        ):
            with self.subTest(plan=plan):
                with self.assertRaisesRegex(ValueError, "Invalid planner response"):
                    validate_plan(plan)


class PlannerGenerationTests(unittest.TestCase):
    @patch("src.agents.planner.generate_response")
    def test_requests_schema_and_returns_validated_plan(self, generate_response):
        plan = make_plan("financial", ["financial_data"])
        generate_response.return_value = json.dumps(plan)
        config = {"model": "test-model"}

        self.assertEqual(generate_plan("  Apple revenue?  ", config), plan)

        generate_response.assert_called_once()
        args, kwargs = generate_response.call_args
        self.assertIs(args[1], config)
        self.assertEqual([message["role"] for message in args[0]], ["system", "user"])
        self.assertEqual(json.loads(args[0][1]["content"]), {"question": "Apple revenue?"})
        self.assertEqual(kwargs, {"response_format": PLANNER_RESPONSE_SCHEMA})

    @patch("src.agents.planner.generate_response")
    def test_invalid_questions_do_not_call_model(self, generate_response):
        for question in (None, True, 12, [], "", " \t\n"):
            with self.subTest(question=question):
                with self.assertRaisesRegex(ValueError, "non-empty string"):
                    generate_plan(question, {})
        generate_response.assert_not_called()

    @patch("src.agents.planner.generate_response", return_value="not JSON")
    def test_rejects_malformed_json(self, generate_response):
        with self.assertRaisesRegex(ValueError, "must be valid JSON") as raised:
            generate_plan("Apple revenue?", {})
        self.assertIsInstance(raised.exception.__cause__, json.JSONDecodeError)

    @patch("src.agents.planner.generate_response")
    def test_model_output_is_validated_before_return(self, generate_response):
        for plan in (None, {}, make_plan("financial", []), make_plan("mixed", ["financial_data"])):
            with self.subTest(plan=plan):
                generate_response.return_value = json.dumps(plan)
                with self.assertRaises(ValueError):
                    generate_plan("Apple revenue?", {})

    @patch("src.agents.planner.generate_response", side_effect=RuntimeError("Model unavailable"))
    def test_model_errors_propagate_without_fabricating_a_plan(self, generate_response):
        with self.assertRaisesRegex(RuntimeError, "Model unavailable"):
            generate_plan("Apple revenue?", {})


if __name__ == "__main__":
    unittest.main()
