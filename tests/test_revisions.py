import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from src.agents.agent_states import create_initial_state
from src.agents.critic import run_critic
from src.agents.revisions import apply_paragraph_patches, numbered_paragraphs, targeted_review_schema
from src.agents.writer import run_writer
from src.verification.agent_answer import VERIFICATION_SCHEMA, build_agent_evidence, build_fact_catalog, compose_template, render_agent_template


class ParagraphPatchTests(unittest.TestCase):
    def test_empty_evidence_and_fact_only_notes_have_valid_review_schema(self):
        schema = targeted_review_schema(VERIFICATION_SCHEMA, [], [])
        Draft202012Validator.check_schema(schema)
        self.assertNotIn("repair_targets", VERIFICATION_SCHEMA["properties"])
        self.assertEqual(schema["properties"]["repair_targets"]["maxItems"], 0)

    def test_unselected_text_separators_kind_and_facts_remain_exact(self):
        original = {"kind": "answer", "text": "First.\n \nSecond.\n\nThird.", "facts": ["1:records/0"]}
        result = apply_paragraph_patches(original, [{"paragraph_id": 2}], {
            "patches": [{"paragraph_id": 2, "text": "Corrected."}],
        })
        self.assertEqual(result, {**original, "text": "First.\n \nCorrected.\n\nThird."})
        self.assertEqual(original["text"], "First.\n \nSecond.\n\nThird.")

    def test_rejects_duplicate_unselected_empty_and_multi_paragraph_patches(self):
        original = {"kind": "answer", "text": "First.\n\nSecond.", "facts": []}
        responses = [
            {"patches": [{"paragraph_id": 1, "text": "Unauthorized"}]},
            {"patches": []},
            {"patches": [{"paragraph_id": 2, "text": " "}]},
            {"patches": [{"paragraph_id": 2, "text": "One\n\nTwo"}]},
            {"patches": [{"paragraph_id": 2, "text": "Replacement"}], "kind": "refusal"},
        ]
        for response in responses:
            with self.subTest(response=response), self.assertRaises((ValueError, ValidationError)):
                apply_paragraph_patches(original, [{"paragraph_id": 2}], response)
        with self.assertRaises(ValueError):
            apply_paragraph_patches(original, [{"paragraph_id": 1}, {"paragraph_id": 2}], {
                "patches": [{"paragraph_id": 1, "text": "A"}, {"paragraph_id": 1, "text": "B"}],
            })


class TargetedRevisionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = create_initial_state("Explain revenue and currency risk.")
        self.state["request_type"] = "mixed"
        self.state["trace"] = [{
            "type": "tool", "status": "completed", "name": "get_company_facts", "arguments": {},
            "result": {"company": {"ticker": "AAPL"}, "records": [
                {"metric": "revenue", "value": 123, "unit": "USD", "fiscal_year": 2025, "end": "2025-09-27"},
            ]},
        }, {
            "type": "tool", "status": "completed", "name": "search_filings", "arguments": {},
            "result": {"matches": [{"text": "Currency changes may affect sales.", "metadata": {"ticker": "AAPL"}}]},
        }]
        self.state["evidence"] = build_agent_evidence(self.state["trace"])
        self.composition = {"kind": "answer", "facts": [], "text":
            "Revenue {{1:records/0/value}} {{1:records/0/unit}}.\n\nCurrency changes reduced sales. [Source 2]"}
        self.state["composition"] = deepcopy(self.composition)
        catalog = build_fact_catalog(self.state["evidence"])
        self.state["draft"] = render_agent_template(compose_template(self.composition, catalog), self.state["evidence"])
        self.targets = [{"paragraph_id": 2, "source_ids": [2], "reason": "A potential effect is not an observed reduction."}]

    @patch("src.verification.agent_answer.generate_response")
    async def test_targeted_critic_locates_error_in_rendered_paragraph(self, generate):
        generate.return_value = json.dumps({"evidence_supported": False, "language_matches": True,
            "answer_complete": True, "issues": ["Observed reduction unsupported"], "repair_targets": self.targets})
        await run_critic(self.state, {}, locate_repairs=True)
        self.assertEqual(self.state["verification"]["repair_targets"], self.targets)
        self.assertIsNone(self.state["answer"])
        payload = json.loads(generate.call_args.args[0][1]["content"])
        self.assertIn("123 USD", payload["paragraphs"][0]["text"])
        self.assertEqual(payload["paragraphs"][1]["paragraph_id"], 2)

    @patch("src.verification.agent_answer.generate_response")
    async def test_patch_keeps_correct_financial_prose_and_still_requires_critic(self, generate):
        generate.return_value = json.dumps({"patches": [{"paragraph_id": 2,
            "text": "Currency changes may affect sales. [Source 2]"}]})
        await run_writer(self.state, {}, {"previous_composition": self.composition,
            "repair_targets": self.targets, "issues": ["Unsupported actual effect"]})
        self.assertEqual(numbered_paragraphs(self.state["composition"]["text"])[0]["text"],
                         numbered_paragraphs(self.composition["text"])[0]["text"])
        self.assertIn("123 USD", self.state["draft"])
        self.assertIsNone(self.state["answer"])
        self.assertIsNone(self.state["verification"])

    @patch("src.verification.agent_answer.generate_response")
    async def test_patch_cannot_bypass_source_rendering(self, generate):
        for text in ("Revenue was 999 USD. [Source 2]", "Risk exists. [Source 999]"):
            with self.subTest(text=text):
                state = deepcopy(self.state)
                generate.return_value = json.dumps({"patches": [{"paragraph_id": 2, "text": text}]})
                with self.assertRaises(ValueError):
                    await run_writer(state, {}, {"previous_composition": self.composition,
                        "repair_targets": self.targets, "issues": ["Correct the claim"]})
                self.assertIsNone(state["answer"])

    @patch("src.verification.agent_answer.generate_response")
    async def test_approval_with_repair_targets_is_an_error_not_a_release(self, generate):
        generate.return_value = json.dumps({"evidence_supported": True, "language_matches": True,
            "answer_complete": True, "issues": [], "repair_targets": self.targets})
        await run_critic(self.state, {}, locate_repairs=True)
        self.assertEqual(self.state["verification"]["status"], "error")
        self.assertIsNone(self.state["answer"])
