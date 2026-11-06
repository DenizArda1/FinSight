import asyncio
import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from src.agents.agent_states import create_initial_state
from src.agents.critic import run_critic
from src.agents.writer import run_writer
from src.verification.agent_answer import (
    VERIFICATION_SCHEMA, build_agent_evidence, build_fact_catalog,
    compose_template, render_agent_template,
)


class CriticTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("src.verification.agent_answer.generate_response")
        self.generate = patcher.start()
        self.addCleanup(patcher.stop)
        self.state = create_initial_state("What is Apple's latest annual revenue?")
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
        self.state["evidence"] = deepcopy(build_agent_evidence(self.state["trace"]))
        self.state["composition"] = {"kind": "answer", "text": "Revenue details follow.", "facts": ["1:records/0"]}
        catalog = build_fact_catalog(self.state["evidence"])
        template = compose_template(self.state["composition"], catalog)
        self.state["draft"] = render_agent_template(template, self.state["evidence"])
        self.approval = {"evidence_supported": True, "language_matches": True, "answer_complete": True, "issues": []}
        self.generate.return_value = json.dumps(self.approval)

    async def test_publishes_only_after_both_checks_pass_and_preserves_sources(self):
        original = deepcopy(self.state)
        result = await run_critic(self.state, {"model": "test-model"})
        self.assertIs(result, self.state)
        self.assertEqual(result["answer"], original["draft"])
        self.assertEqual(result["verification"]["status"], "passed")
        self.assertTrue(result["verification"]["supported"])
        self.assertEqual(result["verification"]["deterministic_fields"], "passed")
        for field in ("draft", "composition", "evidence", "revision_count"):
            self.assertEqual(result[field], original[field])
        self.assertEqual(result["trace"][0], original["trace"][0])
        self.assertEqual(result["trace"][-1]["verification_status"], "passed")
        self.assertEqual(result["trace"][-2]["phase"], "critic")
        self.generate.assert_called_once()
        payload = json.loads(self.generate.call_args.args[0][1]["content"])
        self.assertEqual(payload["answer"], original["draft"])
        self.assertEqual(payload["tool_evidence"], original["evidence"])
        self.assertEqual(payload["prose_for_language_check"], original["composition"]["text"])
        self.assertEqual(self.generate.call_args.kwargs["response_format"], VERIFICATION_SCHEMA)

    async def test_changed_number_period_form_or_citation_is_rejected_without_model(self):
        for old, new in (("416161000000", "999000000000"), ("FY2025", "FY2023"),
                         ("2025-09-27", "2023-09-30"), ("10-K", "10-K/A"),
                         ("[Source 1]", "[Source 2]")):
            with self.subTest(change=new):
                state = deepcopy(self.state)
                state["draft"] = state["draft"].replace(old, new)
                state["answer"] = "Previously released answer"
                await run_critic(state, {})
                self.assertEqual(state["verification"]["status"], "failed")
                self.assertEqual(state["verification"]["deterministic_fields"], "failed")
                self.assertIsNone(state["answer"])
                self.assertEqual(state["trace"][-1]["verification_status"], "failed")
        self.generate.assert_not_called()

    async def test_writer_and_critic_share_expanded_excerpt_under_same_source_id(self):
        state = create_initial_state("What could prevent sales?")
        match = {
            "chunk_id": "report:1", "text": "prevent sales.", "distance": 0.1,
            "metadata": {"ticker": "AAPL", "section": "Item 1A", "start": 31, "end": 45},
            "context": {"text": "Failure to obtain licenses may prevent sales.", "start": 0, "end": 45},
        }
        state["trace"].append({
            "type": "tool", "status": "completed", "name": "search_filings",
            "arguments": {"ticker": "AAPL", "query": "What could prevent sales?"},
            "result": {"company": {"ticker": "AAPL"}, "matches": [match]},
        })
        self.generate.side_effect = [
            json.dumps({"kind": "answer", "text": "Failure to obtain licenses may prevent sales [Source 1].", "facts": []}),
            json.dumps(self.approval),
        ]
        await run_writer(state, {})
        await run_critic(state, {})
        self.assertEqual(self.generate.call_count, 2)
        writer_payload = json.loads(self.generate.call_args_list[0].args[0][1]["content"])
        critic_payload = json.loads(self.generate.call_args_list[1].args[0][1]["content"])
        self.assertEqual(writer_payload["tool_evidence"], critic_payload["tool_evidence"])
        evidence = critic_payload["tool_evidence"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["source_id"], 1)
        self.assertEqual(evidence[0]["result"]["matches"][0]["text"],
                         "<filing_excerpt>\nFailure to obtain licenses may prevent sales.\n</filing_excerpt>")
        self.assertEqual(state["evidence"][0]["result"]["matches"][0], match)
        self.assertEqual(state["answer"], state["draft"])

    async def test_localized_citation_still_requires_semantic_approval(self):
        for supported in (True, False):
            with self.subTest(supported=supported):
                state = deepcopy(self.state)
                composition = {**state["composition"], "text": "Gelir bilgileri [Kaynak 1]."}
                verdict = {
                    **self.approval, "evidence_supported": supported,
                    "issues": [] if supported else ["The claim is not supported by this source."],
                }
                self.generate.side_effect = [json.dumps(composition), json.dumps(verdict)]
                await run_writer(state, {})
                await run_critic(state, {})
                self.assertEqual(state["verification"]["deterministic_fields"], "passed")
                self.assertEqual(state["verification"]["status"], "passed" if supported else "failed")
                self.assertIn("[Source 1]", state["draft"])
                if supported:
                    self.assertEqual(state["answer"], state["draft"])
                else:
                    self.assertIsNone(state["answer"])

    async def test_changed_evidence_or_trace_invalidates_writer_snapshot(self):
        for target in ("evidence", "trace"):
            with self.subTest(target=target):
                state = deepcopy(self.state)
                state[target][0]["result"]["records"][0]["value"] = 999
                await run_critic(state, {})
                self.assertEqual(state["verification"]["status"], "failed")
                self.assertIn("evidence does not match", state["verification"]["issues"][0])
                self.assertIsNone(state["answer"])
        self.generate.assert_not_called()

    async def test_invalid_composition_cannot_bypass_deterministic_checks(self):
        for changes in ({"facts": ["99:records/0"]}, {"extra": True}, {"kind": "unknown"},
                        {"text": "Revenue is 999 USD."}):
            with self.subTest(changes=changes):
                state = deepcopy(self.state)
                state["composition"].update(changes)
                await run_critic(state, {})
                self.assertEqual(state["verification"]["status"], "failed")
                self.assertIsNone(state["answer"])
        self.generate.assert_not_called()

    async def test_unsupported_claim_or_wrong_language_withholds_answer(self):
        for supported, language in ((False, True), (True, False), (False, False)):
            with self.subTest(supported=supported, language=language):
                state = deepcopy(self.state)
                state["answer"] = "Stale answer"
                state["verification"] = {"status": "passed", "supported": True}
                self.generate.return_value = json.dumps({
                    "evidence_supported": supported, "language_matches": language, "answer_complete": True,
                    "issues": ["Unsupported claim or wrong language"],
                })
                await run_critic(state, {})
                self.assertEqual(state["verification"]["status"], "failed")
                self.assertEqual(state["verification"]["deterministic_fields"], "passed")
                self.assertFalse(state["verification"]["supported"])
                self.assertIsNone(state["answer"])

    async def test_malformed_verdict_is_error_not_approval(self):
        payloads = [
            None, [], {}, {**self.approval, "evidence_supported": "true"},
            {key: value for key, value in self.approval.items() if key != "answer_complete"},
            {**self.approval, "answer_complete": "true"},
            {**self.approval, "language_matches": 1}, {**self.approval, "extra": True},
            {**self.approval, "evidence_supported": False, "issues": [" "]},
        ]
        for response in ["not JSON", *[json.dumps(payload) for payload in payloads]]:
            with self.subTest(response=response):
                state = deepcopy(self.state)
                state["answer"] = "Stale answer"
                self.generate.return_value = response
                await run_critic(state, {})
                self.assertEqual(state["verification"]["status"], "error")
                self.assertFalse(state["verification"]["supported"])
                self.assertEqual(state["verification"]["deterministic_fields"], "passed")
                self.assertIsNone(state["answer"])
                self.assertEqual(state["trace"][-1]["status"], "error")

    async def test_inconsistent_verdict_is_revisable_failure_not_approval(self):
        for changes in ({"answer_complete": False}, {"language_matches": False},
                        {"evidence_supported": False}, {"issues": ["Contradiction"]}):
            with self.subTest(changes=changes):
                state = deepcopy(self.state)
                self.generate.return_value = json.dumps({**self.approval, **changes})
                await run_critic(state, {})
                self.assertEqual(state["verification"]["status"], "failed")
                self.assertTrue(state["verification"]["issues"])
                self.assertIsNone(state["answer"])

    async def test_model_failure_is_recorded_and_never_releases_stale_answer(self):
        self.state["answer"] = "Stale answer"
        self.generate.side_effect = RuntimeError("Model disconnected")
        result = await run_critic(self.state, {})
        self.assertIs(result, self.state)
        self.assertEqual(result["verification"]["status"], "error")
        self.assertIn("Model disconnected", result["verification"]["issues"][0])
        self.assertIsNone(result["answer"])
        self.assertEqual(result["trace"][-2]["type"], "model")
        self.assertEqual(result["trace"][-2]["status"], "error")

    async def test_cancellation_is_not_masked_by_trace_cleanup(self):
        self.state["answer"] = "Stale answer"
        self.generate.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await run_critic(self.state, {})
        self.assertIsNone(self.state["answer"])
        self.assertEqual(self.state["verification"]["status"], "error")
        self.assertEqual(self.state["trace"][-1]["verification_status"], "error")

    async def test_missing_draft_or_composition_is_preparation_error(self):
        for field, value in (("draft", None), ("draft", " "), ("composition", None)):
            with self.subTest(field=field, value=value):
                state = deepcopy(self.state)
                state[field] = value
                state["answer"] = "Stale answer"
                await run_critic(state, {})
                self.assertEqual(state["verification"]["status"], "error")
                self.assertEqual(state["verification"]["stage"], "prepare")
                self.assertIsNone(state["answer"])
        self.generate.assert_not_called()

    async def test_source_free_refusal_and_clarification_still_require_judge_approval(self):
        for kind, text in (("refusal", "I cannot provide investment advice."), ("clarification", "Which company?")):
            with self.subTest(kind=kind):
                state = create_initial_state("Question")
                state["composition"] = {"kind": kind, "text": text, "facts": []}
                state["draft"] = text
                await run_critic(state, {})
                self.assertEqual(state["answer"], text)
                self.assertEqual(state["verification"]["status"], "passed")
        self.assertEqual(self.generate.call_count, 2)

    async def test_source_free_factual_answer_is_rejected_before_judge(self):
        state = create_initial_state("Question")
        state["composition"] = {"kind": "answer", "text": "Revenue increased.", "facts": []}
        state["draft"] = "Revenue increased."
        await run_critic(state, {})
        self.assertEqual(state["verification"]["status"], "failed")
        self.assertIsNone(state["answer"])
        self.generate.assert_not_called()

    async def test_comparison_fact_cards_cannot_pass_without_an_explanation(self):
        self.state["request_type"] = "comparison"
        self.state["composition"]["text"] = ""
        catalog = build_fact_catalog(self.state["evidence"])
        self.state["draft"] = render_agent_template(
            compose_template(self.state["composition"], catalog), self.state["evidence"],
        )
        await run_critic(self.state, {})
        self.assertEqual(self.state["verification"]["status"], "failed")
        self.assertIsNone(self.state["answer"])
        self.generate.assert_not_called()

    async def test_writer_then_critic_preserves_draft_and_releases_it_only_after_approval(self):
        composition = deepcopy(self.state["composition"])
        self.generate.side_effect = [json.dumps(composition), json.dumps(self.approval)]
        await run_writer(self.state, {})
        self.assertIsNone(self.state["answer"])
        draft = self.state["draft"]
        await run_critic(self.state, {})
        self.assertEqual(self.state["answer"], draft)
        phases = [event["phase"] for event in self.state["trace"] if event["type"] == "model"]
        self.assertEqual(phases, ["writer", "critic"])

    async def test_supported_but_incomplete_answer_is_withheld(self):
        self.state["question"] = "What is Apple's latest revenue and what risks does its report describe?"
        self.generate.return_value = json.dumps({
            **self.approval, "answer_complete": False,
            "issues": ["The requested risk summary is missing."],
        })
        await run_critic(self.state, {})
        self.assertEqual(self.state["verification"]["status"], "failed")
        self.assertTrue(self.state["verification"]["evidence_supported"])
        self.assertTrue(self.state["verification"]["language_matches"])
        self.assertFalse(self.state["verification"]["answer_complete"])
        self.assertIsNone(self.state["answer"])


if __name__ == "__main__":
    unittest.main()
