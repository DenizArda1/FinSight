import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from src.agents.agent_states import create_initial_state
from src.agents.writer import run_writer
from src.verification.agent_answer import build_agent_evidence


class WriterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("src.verification.agent_answer.generate_response")
        self.generate = patcher.start()
        self.addCleanup(patcher.stop)
        self.state = create_initial_state("Apple'ın son yıllık geliri nedir?")
        self.record = {
            "metric": "revenue", "value": 416161000000, "unit": "USD", "fiscal_year": 2025,
            "end": "2025-09-27", "form": "10-K", "accn": "0000320193-25-000079",
            "source_url": "https://example.com/report",
        }
        self.event = {
            "type": "tool", "status": "completed", "name": "get_company_facts",
            "arguments": {"cik": "0000320193", "concept": "revenue", "years": 1},
            "result": {"company": {"ticker": "AAPL"}, "records": [self.record]},
        }
        self.state["trace"].append(self.event)
        self.composition = {
            "kind": "answer", "text": "Gelir bilgileri aşağıdadır.", "facts": ["1:records/0"],
        }
        self.generate.return_value = json.dumps(self.composition)

    async def test_renders_source_fields_into_draft_without_releasing_answer(self):
        original_event = deepcopy(self.event)
        result = await run_writer(self.state, {"model": "test-model"})
        self.assertIs(result, self.state)
        for value in ("416161000000", "USD", "FY2025", "2025-09-27", "10-K", "[Source 1]"):
            self.assertIn(value, result["draft"])
        self.assertEqual(result["composition"], self.composition)
        self.assertIsNone(result["answer"])
        self.assertIsNone(result["verification"])
        self.assertEqual(self.event, original_event)
        self.assertEqual(result["evidence"], build_agent_evidence([original_event]))
        self.assertEqual(result["trace"][-1]["status"], "completed")
        self.assertEqual(result["trace"][-2]["phase"], "writer")
        self.generate.assert_called_once()
        messages = self.generate.call_args.args[0]
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["question"], self.state["question"])
        self.assertEqual(payload["tool_evidence"], result["evidence"])
        self.assertEqual(self.generate.call_args.kwargs["response_format"]["properties"]["facts"]["items"]["enum"], ["1:records/0"])
        self.record["value"] = 999
        self.assertEqual(result["evidence"][0]["result"]["records"][0]["value"], 416161000000)

    async def test_ignores_failed_tools_specialist_summaries_and_previous_writer_outputs(self):
        self.state["trace"].insert(0, {
            "type": "tool", "status": "error", "name": "get_company_facts",
            "result": {"records": [{"value": 999}]},
        })
        self.state["financial_results"] = [{"summary": "UNSUPPORTED_SUMMARY"}]
        self.state["trace"].append({"type": "model", "phase": "writer", "content": "OLD_WRITER_TEXT"})
        await run_writer(self.state, {})
        message = self.generate.call_args.args[0][1]["content"]
        self.assertNotIn("UNSUPPORTED_SUMMARY", message)
        self.assertNotIn("OLD_WRITER_TEXT", message)
        self.assertEqual(len(self.state["evidence"]), 1)
        self.assertEqual(self.state["evidence"][0]["source_id"], 1)

    async def test_combined_trace_assigns_distinct_sources_to_report_chunks(self):
        self.state["trace"].append({
            "type": "tool", "status": "completed", "name": "search_filings",
            "arguments": {"ticker": "AAPL", "latest": True},
            "result": {"matches": [
                {"text": "First risk.", "metadata": {"section": "Item 1A"}},
                {"text": "Second risk.", "metadata": {"section": "Item 1A"}},
            ]},
        })
        await run_writer(self.state, {})
        self.assertEqual([item["source_id"] for item in self.state["evidence"]], [1, 2, 3])
        self.assertEqual(self.state["evidence"][2]["result"]["matches"][0]["text"], "Second risk.")

    async def test_malformed_json_clears_stale_answer_and_records_failure(self):
        self.state.update(draft="Old draft", answer="Old answer", composition={"old": True},
                          verification={"supported": True}, evidence=[{"old": True}])
        self.generate.return_value = "not JSON"
        with self.assertRaises(json.JSONDecodeError):
            await run_writer(self.state, {})
        for field in ("draft", "answer", "composition", "verification"):
            self.assertIsNone(self.state[field])
        self.assertNotIn({"old": True}, self.state["evidence"])
        self.assertEqual(self.state["trace"][-1]["stage"], "parse")

    async def test_schema_rejects_extra_fields_unknown_facts_and_invalid_types(self):
        payloads = [
            {**self.composition, "extra": "unexpected"},
            {**self.composition, "kind": "unknown"},
            {**self.composition, "facts": ["99:records/0"]},
            {**self.composition, "facts": ["1:records/0", "1:records/0"]},
            {**self.composition, "text": None}, [],
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.generate.return_value = json.dumps(payload)
                with self.assertRaisesRegex(ValueError, "Invalid writer response"):
                    await run_writer(self.state, {})
                self.assertIsNone(self.state["draft"])
                self.assertIsNone(self.state["composition"])
                self.assertIsNone(self.state["answer"])
                self.assertEqual(self.state["trace"][-1]["stage"], "schema")

    async def test_fabricated_numbers_citations_and_field_insertions_are_rejected(self):
        for text in ("Revenue is 999 USD.", "Claim [Source 99].", "{{1:records/0/value}}", "https://invented.example"):
            with self.subTest(text=text):
                self.generate.return_value = json.dumps({**self.composition, "text": text})
                with self.assertRaises(ValueError):
                    await run_writer(self.state, {})
                self.assertIsNone(self.state["draft"])
                self.assertIsNone(self.state["answer"])
                self.assertEqual(self.state["trace"][-1]["stage"], "deterministic")

    async def test_source_free_clarification_and_refusal_remain_unverified_drafts(self):
        for kind, text in (("clarification", "Which company?"), ("refusal", "I cannot provide investment advice.")):
            with self.subTest(kind=kind):
                state = create_initial_state("Question")
                self.generate.return_value = json.dumps({"kind": kind, "text": text, "facts": []})
                await run_writer(state, {})
                self.assertEqual(state["draft"], text)
                self.assertEqual(state["evidence"], [])
                self.assertIsNone(state["answer"])
                self.assertIsNone(state["verification"])

    async def test_factual_answer_without_tool_evidence_is_rejected(self):
        state = create_initial_state("Question")
        self.generate.return_value = json.dumps({"kind": "answer", "text": "Revenue increased.", "facts": []})
        with self.assertRaisesRegex(ValueError, "requires tool evidence"):
            await run_writer(state, {})
        self.assertIsNone(state["draft"])
        self.assertIsNone(state["answer"])

    async def test_model_failure_preserves_error_trace_and_propagates(self):
        error = RuntimeError("Model disconnected")
        self.generate.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            await run_writer(self.state, {})
        self.assertIs(raised.exception, error)
        self.assertEqual(self.state["trace"][-2]["type"], "model")
        self.assertEqual(self.state["trace"][-2]["status"], "error")
        self.assertEqual(self.state["trace"][-1]["agent"], "writer")
        self.assertEqual(self.state["trace"][-1]["status"], "error")
        self.assertIsNone(self.state["draft"])
        self.assertIsNone(self.state["answer"])


if __name__ == "__main__":
    unittest.main()
