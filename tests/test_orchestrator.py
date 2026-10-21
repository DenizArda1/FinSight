import json
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch

from src.agents.orchestrator import run_orchestrator
from src.agents.runtime import run_mcp_orchestrator
from src.tools.agentic_tools import TOOL_SCHEMAS
from src.verification.agent_answer import build_agent_evidence


def tool_message(name, arguments):
    return {
        "role": "assistant", "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


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
        self.planner.assert_called_once_with("Apple revenue and risks?", self.config)
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
        self.assertEqual(trace[2:], financial["trace"] + filing["trace"])
        transitions = [(event["agent"], event["status"]) for event in trace if event["type"] == "agent"]
        self.assertEqual(transitions, [
            ("planner", "started"), ("planner", "completed"),
            ("financial_data", "started"), ("financial_data", "completed"),
            ("filing_rag", "started"), ("filing_rag", "completed"),
        ])
        evidence = build_agent_evidence(trace)
        self.assertEqual([source["source_id"] for source in evidence], [1, 2, 3])
        self.assertEqual(evidence[1]["result"], self.records)
        self.assertEqual(evidence[2]["result"], self.report)
        for tool_call in self.call_tool.await_args_list:
            self.assertIs(tool_call.args[0], self.client)
        self.assertIsNone(state["answer"])
        self.assertIsNone(state["draft"])
        self.assertIsNone(state["verification"])
        json.dumps(state, allow_nan=False)

    async def test_non_research_plans_do_not_run_specialists(self):
        for request_type in ("out_of_scope", "clarification"):
            with self.subTest(request_type=request_type):
                self.planner.return_value = {"request_type": request_type, "tasks": []}
                state = await run_orchestrator("Question", self.config, self.client, TOOL_SCHEMAS)
                self.assertEqual(state["request_type"], request_type)
                self.assertEqual(state["financial_results"], [])
                self.assertEqual(state["filing_results"], [])
                self.assertEqual(len(state["trace"]), 2)
                self.assertIsNone(state["answer"])
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
        first = await run_orchestrator("First question", self.config, self.client, TOOL_SCHEMAS)
        second = await run_orchestrator("Second question", self.config, self.client, TOOL_SCHEMAS)
        for field in ("plan", "financial_results", "filing_results", "trace"):
            self.assertIsNot(first[field], second[field])


class OrchestratorConnectionTests(unittest.IsolatedAsyncioTestCase):
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
