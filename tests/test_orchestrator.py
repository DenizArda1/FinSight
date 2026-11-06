import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
from unittest.mock import AsyncMock, patch

from src.agents.orchestrator import run_orchestrator
from src.agents.runtime import run_mcp_orchestrator
from src.agents.writer import run_writer
from src.tools.agentic_tools import TOOL_SCHEMAS
from src.verification.agent_answer import build_agent_evidence
from src.verification.evidence import evidence_for_prompt


def tool_message(name, arguments):
    return {
        "role": "assistant", "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


async def write_with_initial_corruption(state, llm_config, feedback=None):
    await run_writer(state, llm_config, feedback=feedback)
    if state["revision_count"] == 0:
        state["draft"] = state["draft"].replace("123 USD", "999 USD")
    return state


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        planner_patcher = patch("src.agents.orchestrator.generate_plan")
        self.planner = planner_patcher.start()
        self.addCleanup(planner_patcher.stop)
        chat_patcher = patch("src.agents.specialist.send_chat_request")
        self.chat = chat_patcher.start()
        self.addCleanup(chat_patcher.stop)
        tool_patcher = patch("src.agents.specialist.call_mcp_tool", new_callable=AsyncMock)
        self.call_tool = tool_patcher.start()
        self.addCleanup(tool_patcher.stop)
        writer_patcher = patch("src.verification.agent_answer.generate_response")
        self.writer_response = writer_patcher.start()
        self.addCleanup(writer_patcher.stop)
        self.composition = {
            "kind": "answer", "text": "Risk evidence is available. [Source 3]",
            "facts": ["2:records/0"],
        }
        self.approval = {"evidence_supported": True, "language_matches": True, "answer_complete": True, "issues": []}
        self.rejection = {"evidence_supported": False, "language_matches": True, "answer_complete": True, "issues": ["Remove unsupported claim"]}
        self.writer_response.side_effect = [json.dumps(self.composition), json.dumps(self.approval)]
        self.client = object()
        self.config = {"model": "test-model"}
        self.plan = {
            "request_type": "mixed",
            "tasks": [
                {"id": "task_1", "agent": "financial_data", "instruction": "Retrieve Apple revenue."},
                {"id": "task_2", "agent": "filing_rag", "instruction": "Retrieve Apple risk evidence."},
            ],
        }
        self.planner.return_value = self.plan
        self.done = {"role": "assistant", "content": "Evidence retrieved."}
        self.chat.side_effect = [
            tool_message("resolve_ticker_to_cik", {"ticker": "AAPL"}),
            tool_message("get_company_facts", {"cik": "0000320193", "concept": "revenue", "years": 1}),
            self.done,
            tool_message("search_filings", {"ticker": "AAPL", "query": "risks"}),
            self.done,
        ]
        self.records = {"records": [{"value": 123, "unit": "USD", "accn": "report-id"}]}
        self.report = {"matches": [{"text": "Risk evidence.", "metadata": {"source_url": "https://example.com/report"}}]}
        self.call_tool.side_effect = [
            {"ticker": "AAPL", "cik": "0000320193", "name": "Apple Inc."},
            self.records, self.report,
        ]

    async def test_mixed_plan_runs_specialists_and_routes_results_with_flat_trace(self):
        original_plan = deepcopy(self.plan)
        trace = []
        state = await run_orchestrator("  Apple revenue and risks?  ", self.config, self.client, TOOL_SCHEMAS, trace=trace)
        self.planner.assert_called_once_with("Apple revenue and risks?", self.config, telemetry={})
        self.assertEqual(state["question"], "Apple revenue and risks?")
        self.assertEqual(state["request_type"], "mixed")
        self.assertEqual(state["plan"], original_plan["tasks"])
        self.assertEqual(self.plan, original_plan)
        self.assertEqual(len(state["financial_results"]), 1)
        self.assertEqual(len(state["filing_results"]), 1)
        financial = state["financial_results"][0]
        filing = state["filing_results"][0]
        self.assertEqual(financial["task_id"], "task_1")
        self.assertEqual(filing["task_id"], "task_2")
        self.assertIs(state["trace"], trace)
        self.assertTrue(all(isinstance(event, dict) for event in trace))
        specialist_trace = financial["trace"] + filing["trace"]
        self.assertEqual(trace[2:2 + len(specialist_trace)], specialist_trace)
        transitions = [(event["agent"], event["status"]) for event in trace if event["type"] == "agent"]
        self.assertEqual(transitions, [
            ("planner", "started"), ("planner", "completed"),
            ("financial_data", "started"), ("financial_data", "completed"),
            ("filing_rag", "started"), ("filing_rag", "completed"),
            ("writer", "started"), ("writer", "completed"),
            ("critic", "started"), ("critic", "completed"),
        ])
        evidence = build_agent_evidence(trace)
        self.assertEqual([source["source_id"] for source in evidence], [1, 2, 3])
        self.assertEqual(evidence[1]["result"], self.records)
        self.assertEqual(evidence[2]["result"], self.report)
        for tool_call in self.call_tool.await_args_list:
            self.assertIs(tool_call.args[0], self.client)
        self.assertEqual(state["answer"], state["draft"])
        self.assertIn("123 USD", state["draft"])
        self.assertIn("[Source 3]", state["draft"])
        self.assertEqual(state["verification"]["status"], "passed")
        self.assertEqual(state["revision_count"], 0)
        self.assertEqual(self.writer_response.call_count, 2)
        writer_input = json.loads(self.writer_response.call_args_list[0].args[0][1]["content"])
        self.assertEqual(writer_input["tool_evidence"], evidence_for_prompt(evidence))
        self.assertEqual(state["evidence"], evidence)
        json.dumps(state, allow_nan=False)

    async def test_non_research_plans_do_not_run_specialists(self):
        for request_type in ("out_of_scope", "clarification"):
            with self.subTest(request_type=request_type):
                self.planner.return_value = {"request_type": request_type, "tasks": []}
                kind = "refusal" if request_type == "out_of_scope" else "clarification"
                composition = {
                    "kind": kind, "text": "Cannot provide investment advice." if kind == "refusal" else "Which company?",
                    "facts": [],
                }
                self.writer_response.side_effect = [json.dumps(composition), json.dumps(self.approval)]
                state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
                self.assertEqual(state["request_type"], request_type)
                self.assertEqual(state["financial_results"], [])
                self.assertEqual(state["filing_results"], [])
                self.assertEqual(state["trace"][-1]["agent"], "critic")
                self.assertEqual(state["trace"][-1]["status"], "completed")
                self.assertEqual(state["composition"]["kind"], kind)
                self.assertTrue(state["draft"])
                self.assertEqual(state["answer"], state["draft"])
                self.assertEqual(state["verification"]["status"], "passed")
        self.chat.assert_not_called()
        self.call_tool.assert_not_awaited()

    async def test_specialist_failure_keeps_prior_and_failed_task_traces(self):
        error = RuntimeError("MCP disconnected")
        self.call_tool.side_effect = [
            {"cik": "0000320193"}, self.records, error,
        ]
        self.plan["tasks"].append({"id": "task_3", "agent": "filing_rag", "instruction": "Retrieve more evidence."})
        trace = []
        with self.assertRaises(RuntimeError) as raised:
            await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS, trace=trace)
        self.assertIs(raised.exception, error)
        self.assertEqual(trace[-1]["task_id"], "task_2")
        self.assertEqual(trace[-1]["status"], "error")
        self.assertEqual(trace[-2]["type"], "tool")
        self.assertEqual(len(build_agent_evidence(trace)), 2)
        self.assertFalse(any(event.get("task_id") == "task_3" for event in trace))
        self.writer_response.assert_not_called()
        json.dumps(trace, allow_nan=False)

    async def test_planner_failure_is_recorded_and_stops_specialists(self):
        error = ValueError("Invalid planner response")
        self.planner.side_effect = error
        trace = []
        with self.assertRaises(ValueError) as raised:
            await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS, trace=trace)
        self.assertIs(raised.exception, error)
        self.assertEqual([event["status"] for event in trace], ["started", "error"])
        self.assertEqual(trace[-1]["error"]["message"], str(error))
        self.chat.assert_not_called()
        self.call_tool.assert_not_awaited()
        self.writer_response.assert_not_called()

    async def test_invalid_question_or_trace_is_rejected_before_planner(self):
        with self.assertRaises(ValueError):
            await run_orchestrator(" ", self.config, self.client, TOOL_SCHEMAS)
        for trace in ({}, "trace", [{"existing": True}]):
            with self.subTest(trace=trace):
                original = deepcopy(trace)
                with self.assertRaises(ValueError):
                    await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS, trace=trace)
                self.assertEqual(trace, original)
        self.planner.assert_not_called()

    async def test_separate_runs_have_independent_states(self):
        self.planner.return_value = {"request_type": "clarification", "tasks": []}
        composition = {"kind": "clarification", "text": "Which company?", "facts": []}
        self.writer_response.side_effect = [json.dumps(composition), json.dumps(self.approval)] * 2
        first = await run_orchestrator("First question", self.config, self.client, TOOL_SCHEMAS)
        second = await run_orchestrator("Second question", self.config, self.client, TOOL_SCHEMAS)
        for field in ("plan", "financial_results", "filing_results", "trace", "evidence", "composition"):
            self.assertIsNot(first[field], second[field])

    async def test_writer_failure_preserves_collected_sources_and_error_trace(self):
        self.writer_response.side_effect = ["not JSON"]
        trace = []
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS, trace=trace, max_revisions=0)
        self.assertEqual(len(build_agent_evidence(trace)), 3)
        self.assertEqual(trace[-2]["agent"], "writer")
        self.assertEqual(trace[-2]["status"], "error")
        self.assertEqual(trace[-2]["stage"], "parse")
        self.assertEqual(trace[-1]["status"], "exhausted")
        self.assertIsNone(state["answer"])
        self.assertEqual(state["verification"]["stage"], "writer_validation")

    async def test_writer_format_failure_uses_same_revision_budget_and_preserves_evidence(self):
        invalid = {**self.composition, "text": "Revenue is 123 USD. Risk evidence follows."}
        self.writer_response.side_effect = [json.dumps(invalid), json.dumps({**self.composition, "text": "Revenue is in USD. Risk evidence follows. [Source 2] [Source 3]"}), json.dumps(self.approval)]
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertEqual(state["revision_count"], 1)
        self.assertEqual(state["verification"]["status"], "passed")
        self.assertIn("123 USD", state["answer"])
        self.assertEqual(self.call_tool.await_count, 3)
        messages = self.writer_response.call_args_list[1].args[0]
        self.assertEqual(json.loads(messages[-2]["content"]), invalid)
        self.assertIn("tool_evidence", json.loads(messages[1]["content"]))
        self.assertEqual(state["composition"]["facts"], invalid["facts"])
        critic_events = [event for event in state["trace"] if event.get("agent") == "critic" and event["status"] == "started"]
        self.assertEqual(len(critic_events), 1)

    async def test_repeated_prose_errors_keep_facts_and_exhaust_original_budget(self):
        invalid = {**self.composition, "text": "The period is 2025."}
        self.writer_response.side_effect = [json.dumps(invalid)] * 3
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertIsNone(state["answer"])
        self.assertEqual(state["revision_count"], 2)
        self.assertEqual(state["trace"][-1]["status"], "exhausted")
        self.assertEqual(self.writer_response.call_count, 3)
        errors = [event for event in state["trace"] if event.get("agent") == "writer" and event["status"] == "error"]
        self.assertEqual(len(errors), 3)
        self.assertTrue(all(event["stage"] == "deterministic" for event in errors))

    async def test_writer_validation_and_critic_rejection_share_two_revision_limit(self):
        self.writer_response.side_effect = [
            "not JSON", json.dumps(self.composition), json.dumps(self.rejection), "not JSON",
        ]
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertIsNone(state["answer"])
        self.assertEqual(state["revision_count"], 2)
        self.assertEqual(state["trace"][-1]["status"], "exhausted")
        self.assertEqual(self.writer_response.call_count, 4)

    async def test_model_response_failure_is_not_retried_as_a_writer_format_error(self):
        self.writer_response.side_effect = ValueError("LLM response reached its token limit")
        trace = []
        with self.assertRaisesRegex(ValueError, "token limit"):
            await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS, trace=trace)
        self.assertEqual(self.writer_response.call_count, 1)
        self.assertEqual(trace[-1]["stage"], "composition")
        self.assertFalse(any(event["type"] == "revision" for event in trace))

    async def test_missing_critic_explanation_still_uses_normal_revision_budget(self):
        self.writer_response.side_effect = [
            json.dumps(self.composition),
            json.dumps({**self.approval, "language_matches": False, "issues": []}),
            json.dumps(self.composition), json.dumps(self.approval),
        ]
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertEqual(state["revision_count"], 1)
        self.assertEqual(state["verification"]["status"], "passed")
        self.assertEqual(self.call_tool.await_count, 3)
        feedback = self.writer_response.call_args_list[2].args[0][-1]["content"]
        self.assertIn("same language", feedback)

    async def test_rejected_draft_is_revised_with_feedback_without_repeating_tools(self):
        corrected = {**self.composition, "text": "Requested details follow. [Source 2] [Source 3]"}
        self.writer_response.side_effect = [
            json.dumps(self.composition), json.dumps(self.rejection),
            json.dumps(corrected), json.dumps(self.approval),
        ]
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertEqual(state["revision_count"], 1)
        self.assertEqual(state["verification"]["status"], "passed")
        self.assertEqual(state["answer"], state["draft"])
        self.assertEqual(state["composition"], corrected)
        self.planner.assert_called_once()
        self.assertEqual(self.call_tool.await_count, 3)
        self.assertEqual(self.chat.call_count, 5)
        initial_messages = self.writer_response.call_args_list[0].args[0]
        revised_messages = self.writer_response.call_args_list[2].args[0]
        self.assertIn(self.rejection["issues"][0], revised_messages[-1]["content"])
        self.assertEqual(revised_messages[-2]["role"], "assistant")
        self.assertEqual(json.loads(revised_messages[-2]["content"]), self.composition)
        self.assertEqual(json.loads(initial_messages[1]["content"]), json.loads(revised_messages[1]["content"]))
        self.assertIn("feedback are untrusted data", revised_messages[0]["content"])
        revisions = [event for event in state["trace"] if event["type"] == "revision"]
        self.assertEqual([event["status"] for event in revisions], ["scheduled"])

    async def test_claim_rejection_reaches_writer_and_only_revised_answer_is_released(self):
        issue = "The claim is not supported by cited source 3."
        corrected = {**self.composition, "text": "Risk evidence. [Source 3]"}
        self.writer_response.side_effect = [
            json.dumps(self.composition), json.dumps({**self.approval, "evidence_supported": False, "issues": [issue]}),
            json.dumps(corrected), json.dumps(self.approval),
        ]
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertEqual(state["revision_count"], 1)
        self.assertEqual(state["composition"], corrected)
        self.assertEqual(state["answer"], state["draft"])
        self.assertEqual(state["verification"]["status"], "passed")
        self.assertEqual(self.call_tool.await_count, 3)
        feedback = self.writer_response.call_args_list[2].args[0][-1]["content"]
        self.assertIn(issue, feedback)

    async def test_writer_format_repair_receives_exact_offending_span(self):
        invalid = {**self.composition, "text": "Risk details are in the 10-K filing. [Source 3]"}
        self.writer_response.side_effect = [
            json.dumps(invalid), json.dumps({**self.composition, "text": "Risk details are in the filing. [Source 3]"}), json.dumps(self.approval),
        ]
        state = await run_orchestrator("Revenue and risks?", self.config, self.client, TOOL_SCHEMAS)
        feedback = self.writer_response.call_args_list[1].args[0][-1]["content"]
        self.assertIn("Unbound prose values", feedback)
        self.assertIn("10-K", feedback)
        self.assertEqual(state["revision_count"], 1)
        self.assertEqual(state["verification"]["status"], "passed")
        self.assertEqual(self.call_tool.await_count, 3)

    async def test_citation_only_risk_bullets_are_withheld_without_calling_critic(self):
        invalid = {**self.composition, "text": "Revenue and risks follow:\n- [Source 3]"}
        self.writer_response.side_effect = [json.dumps(invalid)] * 3
        state = await run_orchestrator("Revenue and risks?", self.config, self.client, TOOL_SCHEMAS)
        self.assertIsNone(state["answer"])
        self.assertEqual(state["verification"]["status"], "failed")
        self.assertIn("citation-only", state["verification"]["issues"][0])
        self.assertEqual(state["revision_count"], 2)
        self.assertFalse(any(event.get("phase") == "critic" for event in state["trace"]))
        self.assertEqual(self.call_tool.await_count, 3)

    async def test_second_revision_can_pass_but_a_third_is_never_attempted(self):
        self.writer_response.side_effect = [
            json.dumps(self.composition), json.dumps(self.rejection),
            json.dumps(self.composition), json.dumps(self.rejection),
            json.dumps(self.composition), json.dumps(self.approval),
        ]
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertEqual(state["revision_count"], 2)
        self.assertEqual(state["verification"]["status"], "passed")
        self.assertEqual(self.writer_response.call_count, 6)

    async def test_missing_risk_summary_triggers_revision_even_when_facts_are_supported(self):
        self.report["matches"][0]["text"] = "Supplier disruptions can delay product availability."
        incomplete = {**self.composition, "text": "Revenue and risks follow. [Source 2] [Source 3]"}
        corrected = {**self.composition, "text": "Supplier disruptions can delay product availability. [Source 3]"}
        verdict = {
            **self.approval, "answer_complete": False,
            "issues": ["The requested risk summary is missing; metadata does not describe risks."],
        }
        self.writer_response.side_effect = [
            json.dumps(incomplete), json.dumps(verdict),
            json.dumps(corrected), json.dumps(self.approval),
        ]
        state = await run_orchestrator("Apple revenue and risks?", self.config, self.client, TOOL_SCHEMAS)
        self.assertEqual(state["revision_count"], 1)
        self.assertTrue(state["verification"]["answer_complete"])
        self.assertIn("Supplier disruptions", state["answer"])
        self.assertIn("123 USD", state["answer"])
        self.assertEqual(self.call_tool.await_count, 3)
        feedback = self.writer_response.call_args_list[2].args[0][-1]["content"]
        self.assertIn(verdict["issues"][0], feedback)

    async def test_exhausted_revisions_withhold_answer_and_preserve_last_issues(self):
        self.writer_response.side_effect = [json.dumps(self.composition), json.dumps(self.rejection)] * 3
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertEqual(state["revision_count"], 2)
        self.assertEqual(self.writer_response.call_count, 6)
        self.assertIsNone(state["answer"])
        self.assertEqual(state["verification"]["status"], "failed")
        self.assertEqual(state["verification"]["issues"], self.rejection["issues"])
        self.assertEqual(state["trace"][-1]["status"], "exhausted")
        self.assertEqual(self.call_tool.await_count, 3)

    async def test_later_format_failure_preserves_unverified_partial_draft(self):
        self.writer_response.side_effect = [json.dumps(self.composition), json.dumps(self.rejection), "bad JSON", "bad JSON"]
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertEqual(state["revision_count"], 2)
        self.assertIsNone(state["answer"])
        self.assertEqual(state["verification"]["status"], "failed")
        self.assertIn("123 USD", state["draft"])
        self.assertEqual(state["composition"], self.composition)
        self.assertIn("earlier unverified draft", " ".join(state["verification"]["issues"]))

    async def test_zero_revision_budget_stops_after_first_rejection(self):
        self.writer_response.side_effect = [json.dumps(self.composition), json.dumps(self.rejection)]
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS, max_revisions=0)
        self.assertEqual(state["revision_count"], 0)
        self.assertEqual(self.writer_response.call_count, 2)
        self.assertIsNone(state["answer"])
        self.assertEqual(state["trace"][-1]["status"], "exhausted")

    async def test_critic_error_stops_without_revision_or_answer(self):
        self.writer_response.side_effect = [json.dumps(self.composition), "invalid verdict"]
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertEqual(state["verification"]["status"], "error")
        self.assertIsNone(state["answer"])
        self.assertEqual(state["revision_count"], 0)
        self.assertFalse(any(event["type"] == "revision" for event in state["trace"]))
        self.assertEqual(self.writer_response.call_count, 2)

    async def test_writer_failure_during_revision_does_not_reuse_rejected_answer(self):
        self.writer_response.side_effect = [json.dumps(self.composition), json.dumps(self.rejection), RuntimeError("Writer disconnected")]
        trace = []
        with self.assertRaisesRegex(RuntimeError, "Writer disconnected"):
            await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS, trace=trace)
        self.assertEqual(self.writer_response.call_count, 3)
        self.assertEqual(trace[-1]["agent"], "writer")
        self.assertEqual(trace[-1]["status"], "error")
        self.assertEqual(len(build_agent_evidence(trace)), 3)

    @patch("src.agents.orchestrator.run_writer", side_effect=write_with_initial_corruption)
    async def test_injected_wrong_number_is_rejected_then_corrected(self, writer):
        self.writer_response.side_effect = [
            json.dumps(self.composition), json.dumps(self.composition), json.dumps(self.approval),
        ]
        state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
        self.assertEqual(writer.await_count, 2)
        self.assertEqual(state["revision_count"], 1)
        self.assertIn("123 USD", state["answer"])
        self.assertNotIn("999 USD", state["answer"])
        self.assertEqual(state["verification"]["status"], "passed")
        decisions = [event for event in state["trace"] if event.get("agent") == "critic" and "verification_status" in event]
        self.assertEqual([event["verification_status"] for event in decisions], ["failed", "passed"])
        messages = self.writer_response.call_args_list[1].args[0]
        self.assertEqual(json.loads(messages[-2]["content"]), self.composition)
        self.assertIn("source-rendered", messages[-1]["content"])

    async def test_revision_budget_is_validated_before_planning(self):
        for budget in (True, -1, 3, "2", 1.5, None):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS, max_revisions=budget)
        self.planner.assert_not_called()


class OrchestratorConnectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        patcher = patch("src.agents.runtime.TRACE_DIRECTORY", Path(temporary.name) / "runs")
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("src.agents.runtime.load_mcp_tool_schemas", new_callable=AsyncMock)
    @patch("src.agents.runtime.Client")
    @patch("src.agents.runtime.run_orchestrator", new_callable=AsyncMock)
    async def test_passes_open_connection_schemas_and_trace_then_closes(self, orchestrator, client_class, load_schemas):
        connection = client_class.return_value
        client = connection.__aenter__.return_value
        load_schemas.return_value = TOOL_SCHEMAS
        orchestrator.return_value = {"answer": None, "financial_results": []}
        config, trace = {"model": "test"}, []

        result = await run_mcp_orchestrator("Question", config, trace=trace)

        load_schemas.assert_awaited_once_with(client)
        orchestrator.assert_awaited_once_with(
            "Question", config, mcp_client=client, tool_schemas=TOOL_SCHEMAS, trace=trace,
        )
        self.assertIs(orchestrator.await_args.kwargs["trace"], trace)
        self.assertIs(result, orchestrator.return_value)
        connection.__aexit__.assert_awaited_once_with(None, None, None)

    @patch("src.agents.runtime.load_mcp_tool_schemas", new_callable=AsyncMock)
    @patch("src.agents.runtime.Client")
    @patch("src.agents.runtime.run_orchestrator", new_callable=AsyncMock)
    async def test_closes_connection_when_orchestrator_fails(self, orchestrator, client_class, load_schemas):
        connection = client_class.return_value
        connection.__aexit__.return_value = False
        error = RuntimeError("Orchestrator failed")
        orchestrator.side_effect = error

        with self.assertRaises(RuntimeError) as raised:
            await run_mcp_orchestrator("Question", {})

        self.assertIs(raised.exception, error)
        connection.__aexit__.assert_awaited_once()
        self.assertIs(connection.__aexit__.await_args.args[1], error)

    @patch("src.agents.runtime.load_mcp_tool_schemas", new_callable=AsyncMock)
    @patch("src.agents.runtime.Client")
    @patch("src.agents.runtime.run_orchestrator", new_callable=AsyncMock)
    async def test_discovery_failure_closes_connection_before_planning(self, orchestrator, client_class, load_schemas):
        connection = client_class.return_value
        connection.__aexit__.return_value = False
        load_schemas.side_effect = ValueError("Missing tool schemas")

        with self.assertRaisesRegex(ValueError, "Missing tool schemas"):
            await run_mcp_orchestrator("Question", {})

        orchestrator.assert_not_awaited()
        connection.__aexit__.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
