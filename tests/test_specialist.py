import json
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, call, patch

from src.agents.specialist import execute_specialist_tool, run_specialist
from src.llm.client import IncompleteResponseError
from src.mcp.client import MCPToolError
from src.tools.agentic_tools import AGENT_TOOL_NAMES, TOOL_SCHEMAS
from src.verification.agent_answer import build_agent_evidence


class SpecialistToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_requested_filing_year_rejects_latest_missing_wrong_or_coerced_years(self):
        cases = [
            ("search_filings", {}),
            ("search_filings", {"latest": True}),
            ("search_filings", {"fiscal_year": 2027}),
            ("search_filings", {"fiscal_year": "2026"}),
            ("search_filings", {"fiscal_year": 2026.0}),
            ("search_filings", {"fiscal_year": 2026, "latest": True}),
            ("search_filings", {"fiscal_year": 2026, "latest": 0}),
            ("get_filing_section", {}),
            ("get_filing_section", {"year": 2027}),
            ("get_filing_section", {"year": "2026"}),
            ("get_filing_section", {"year": True}),
        ]
        for tool, arguments in cases:
            with self.subTest(tool=tool, arguments=arguments), self.assertRaisesRegex(ValueError, "2026"):
                await execute_specialist_tool("filing_rag", tool, arguments, self.client, set(), requested_fiscal_year=2026)
        self.call_tool.assert_not_awaited()

    async def test_requested_year_is_forwarded_without_rewriting_arguments(self):
        self.call_tool.return_value = {"matches": []}
        for tool, args in (("search_filings", {"ticker": "NVDA", "query": "Risk", "fiscal_year": 2026}),
                           ("get_filing_section", {"ticker": "NVDA", "year": 2026, "section": "Item 1A"})):
            original = deepcopy(args)
            result = await execute_specialist_tool("filing_rag", tool, args, self.client, set(), requested_fiscal_year=2026)
            self.call_tool.assert_awaited_with(self.client, tool, original)
            self.assertEqual(args, original)
            self.assertEqual(result, {"matches": []})

    def setUp(self):
        patcher = patch("src.agents.specialist.call_mcp_tool", new_callable=AsyncMock)
        self.call_tool = patcher.start()
        self.addCleanup(patcher.stop)
        self.client = object()
        self.cik = "0000320193"

    async def test_resolution_enables_financial_calls_and_preserves_raw_results(self):
        company = {"ticker": "AAPL", "cik": self.cik, "name": "Apple Inc."}
        facts = {"records": [{"value": 123, "unit": "USD", "accn": "source-id"}]}
        self.call_tool.side_effect = [company, facts]
        resolved_ciks = set()
        self.assertEqual(await execute_specialist_tool(
            "financial_data", "resolve_ticker_to_cik", {"ticker": "AAPL"},
            self.client, resolved_ciks,
        ), company)
        self.assertEqual(resolved_ciks, {self.cik})

        arguments = {"cik": self.cik, "concept": "revenue", "years": 1}
        original = deepcopy(arguments)
        result = await execute_specialist_tool(
            "financial_data", "get_company_facts", arguments, self.client, resolved_ciks,
        )
        self.assertEqual(result, facts)
        self.assertEqual(arguments, original)
        self.assertEqual(self.call_tool.await_args_list, [
            call(self.client, "resolve_ticker_to_cik", {"ticker": "AAPL"}),
            call(self.client, "get_company_facts", arguments),
        ])

    async def test_unknown_agents_and_forbidden_tools_never_reach_mcp(self):
        cases = [
            ("unknown", "resolve_ticker_to_cik"),
            (None, "resolve_ticker_to_cik"),
            ([], "resolve_ticker_to_cik"),
            ("financial_data", "search_filings"),
            ("financial_data", "get_filing_section"),
            ("filing_rag", "get_company_facts"),
            ("filing_rag", "compute_metrics"),
            ("financial_data", "unknown"),
            ("financial_data", []),
        ]
        for agent, tool in cases:
            with self.subTest(agent=agent, tool=tool):
                with self.assertRaises(ValueError):
                    await execute_specialist_tool(agent, tool, {}, self.client, set())
        self.call_tool.assert_not_awaited()

    async def test_unresolved_or_invalid_ciks_never_reach_mcp(self):
        for tool in ("get_company_facts", "compute_metrics"):
            for cik in (None, "0001018724", [], {}, True, 320193):
                with self.subTest(tool=tool, cik=cik):
                    with self.assertRaisesRegex(ValueError, "Resolve the ticker"):
                        await execute_specialist_tool(
                            "financial_data", tool, {"cik": cik}, self.client, {self.cik},
                        )
        self.call_tool.assert_not_awaited()

    async def test_invalid_arguments_and_resolution_state_are_rejected_before_mcp(self):
        for arguments, resolved in ((None, set()), ([], set()), ("{}", set()), ({}, [])):
            with self.subTest(arguments=arguments, resolved=resolved):
                with self.assertRaises(ValueError):
                    await execute_specialist_tool(
                        "financial_data", "resolve_ticker_to_cik", arguments,
                        self.client, resolved,
                    )
        self.call_tool.assert_not_awaited()

    async def test_missing_or_invalid_resolution_does_not_change_known_ciks(self):
        for result in ({}, {"cik": None}, {"cik": ""}, {"cik": " \t"}, {"cik": 320193}):
            with self.subTest(result=result):
                self.call_tool.return_value = result
                resolved = {"0001018724"}
                with self.assertRaisesRegex(ValueError, "non-empty CIK string"):
                    await execute_specialist_tool(
                        "financial_data", "resolve_ticker_to_cik", {"ticker": "AAPL"},
                        self.client, resolved,
                    )
                self.assertEqual(resolved, {"0001018724"})

    async def test_allowed_report_and_calculation_tools_return_unchanged_results(self):
        for agent, tool, arguments in (
            ("financial_data", "compute_metrics", {"cik": self.cik, "metrics": ["net_margin"]}),
            ("filing_rag", "search_filings", {"ticker": "AAPL", "query": "risks"}),
            ("filing_rag", "get_filing_section", {"ticker": "AAPL", "year": 2025, "section": "Item 1A"}),
        ):
            with self.subTest(agent=agent, tool=tool):
                result = {"company": {"cik": "0001018724"}, "source": "preserved"}
                self.call_tool.return_value = result
                resolved = {self.cik}
                self.assertEqual(await execute_specialist_tool(
                    agent, tool, arguments, self.client, resolved,
                ), result)
                self.call_tool.assert_awaited_with(self.client, tool, arguments)
                self.assertEqual(resolved, {self.cik})

    async def test_tool_and_connection_errors_propagate_without_marking_resolution(self):
        for error in (MCPToolError("Unknown ticker"), RuntimeError("Disconnected")):
            with self.subTest(error=error):
                self.call_tool.side_effect = error
                resolved = set()
                with self.assertRaises(type(error)) as raised:
                    await execute_specialist_tool(
                        "financial_data", "resolve_ticker_to_cik", {"ticker": "AAPL"},
                        self.client, resolved,
                    )
                self.assertIs(raised.exception, error)
                self.assertEqual(resolved, set())

    async def test_resolution_does_not_leak_between_tasks(self):
        self.call_tool.return_value = {"cik": self.cik}
        await execute_specialist_tool(
            "filing_rag", "resolve_ticker_to_cik", {"ticker": "AAPL"}, self.client, set(),
        )
        self.call_tool.reset_mock()
        with self.assertRaisesRegex(ValueError, "Resolve the ticker"):
            await execute_specialist_tool(
                "financial_data", "get_company_facts", {"cik": self.cik}, self.client, set(),
            )
        self.call_tool.assert_not_awaited()


def model_tool_message(name, arguments):
    return {
        "role": "assistant", "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


class SpecialistLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_section_gets_scoped_search_without_losing_raw_source(self):
        task = {"id": "risk", "agent": "filing_rag", "instruction": "Explain export risks.", "fiscal_year": 2026}
        arguments = {"ticker": "NVDA", "year": 2026, "section": "Item 1A"}
        section = {"text": "Long source paragraph. " * 400, "metadata": {"section": "Item 1A", "fiscal_year": 2026}}
        matches = {"matches": [{"text": "Export restrictions may delay shipments.", "metadata": {"section": "Item 1A"}}]}
        self.chat.side_effect = [model_tool_message("get_filing_section", arguments), self.done]
        self.call_tool.side_effect = [section, matches]
        result = await run_specialist(task, {}, self.client, TOOL_SCHEMAS)
        self.assertEqual(result["tool_call_count"], 2)
        self.call_tool.assert_awaited_with(self.client, "search_filings", {
            "ticker": "NVDA", "fiscal_year": 2026, "section": "Item 1A",
            "query": task["instruction"], "top_k": 3,
        })
        events = [event for event in result["trace"] if event["type"] == "tool"]
        self.assertEqual(events[0]["result"], section)
        self.assertEqual(events[1]["origin"], "section_context_fallback")
        messages = self.chat.call_args_list[1].args[0]
        section_reply = next(message for message in messages if message.get("tool_name") == "get_filing_section")
        self.assertNotIn(section["text"], section_reply["content"])
        self.assertIn("content_limit", section_reply["content"])
        evidence = build_agent_evidence(result["trace"])
        self.assertTrue(evidence[0]["content_omitted"])
        self.assertEqual(evidence[1]["result"], matches)

    async def test_section_search_fallback_obeys_tool_call_budget(self):
        task = {"id": "risk", "agent": "filing_rag", "instruction": "Explain risks.", "fiscal_year": 2026}
        self.chat.return_value = model_tool_message("get_filing_section", {"ticker": "NVDA", "year": 2026, "section": "Item 1A"})
        self.call_tool.return_value = {"text": "Long section. " * 600, "metadata": {}}
        with self.assertRaisesRegex(RuntimeError, "maximum number of tool calls"):
            await run_specialist(task, {}, self.client, TOOL_SCHEMAS, max_tool_calls=1)
        self.call_tool.assert_awaited_once()

    def setUp(self):
        chat_patcher = patch("src.agents.specialist.send_chat_request")
        self.chat = chat_patcher.start()
        self.addCleanup(chat_patcher.stop)
        tool_patcher = patch("src.agents.specialist.call_mcp_tool", new_callable=AsyncMock)
        self.call_tool = tool_patcher.start()
        self.addCleanup(tool_patcher.stop)
        self.task = {"id": "task_1", "agent": "financial_data", "instruction": "Retrieve Apple revenue."}
        self.client = object()
        self.company = {"ticker": "AAPL", "cik": "0000320193", "name": "Apple Inc."}
        self.resolve = model_tool_message("resolve_ticker_to_cik", {"ticker": "AAPL"})
        self.facts = model_tool_message("get_company_facts", {
            "cik": self.company["cik"], "concept": "revenue", "years": 1,
        })
        self.done = {"role": "assistant", "content": "Evidence retrieved."}

    async def test_collects_raw_evidence_and_filters_tools_without_persisting_thinking(self):
        records = {"records": [{"value": 123, "unit": "USD", "accn": "source-id"}]}
        self.chat.side_effect = [{**self.resolve, "thinking": "private reasoning"}, self.facts, self.done]
        self.call_tool.side_effect = [self.company, records]
        result = await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS)
        self.assertEqual(result["summary"], "Evidence retrieved.")
        self.assertEqual(result["tool_call_count"], 2)
        self.assertEqual([item["result"] for item in build_agent_evidence(result["trace"])], [self.company, records])
        for event in result["trace"]:
            self.assertEqual(event["task_id"], self.task["id"])
            self.assertEqual(event["agent"], self.task["agent"])
        self.assertNotIn("private reasoning", json.dumps(result))
        for chat_call in self.chat.call_args_list:
            tools = chat_call.kwargs["tools"]
            self.assertEqual({item["function"]["name"] for item in tools}, AGENT_TOOL_NAMES["financial_data"])
        messages = self.chat.call_args.args[0]
        tool_messages = [message for message in messages if message["role"] == "tool"]
        self.assertEqual(json.loads(tool_messages[-1]["content"]), records)
        records["records"][0]["value"] = 999
        self.assertEqual(build_agent_evidence(result["trace"])[1]["result"]["records"][0]["value"], 123)

    async def test_recovers_after_permission_and_unresolved_cik_errors(self):
        forbidden = model_tool_message("search_filings", {"ticker": "AAPL", "query": "risks"})
        self.chat.side_effect = [forbidden, self.facts, self.resolve, self.facts, self.done]
        self.call_tool.side_effect = [self.company, {"records": []}]
        result = await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS)
        self.assertEqual(result["tool_call_count"], 4)
        self.assertEqual(self.call_tool.await_count, 2)
        events = [event for event in result["trace"] if event["type"] == "tool"]
        self.assertEqual([event["status"] for event in events], ["error", "error", "completed", "completed"])
        messages = self.chat.call_args.args[0]
        feedback = [json.loads(message["content"]) for message in messages if message["role"] == "tool"]
        self.assertIn("not allowed", feedback[0]["error"]["message"])
        self.assertIn("Resolve the ticker", feedback[1]["error"]["message"])
        self.assertEqual(len(build_agent_evidence(result["trace"])), 2)

    async def test_mcp_tool_error_is_returned_to_model(self):
        self.chat.side_effect = [self.resolve, self.resolve, self.done]
        self.call_tool.side_effect = [MCPToolError("Temporary tool error"), self.company]
        result = await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS)
        self.assertEqual(result["tool_call_count"], 2)
        self.assertEqual(len(build_agent_evidence(result["trace"])), 1)

    async def test_invalid_arguments_can_be_corrected(self):
        self.chat.side_effect = [model_tool_message("resolve_ticker_to_cik", "AAPL"), self.resolve, self.done]
        self.call_tool.return_value = self.company
        result = await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS)
        self.assertEqual(result["tool_call_count"], 2)
        self.call_tool.assert_awaited_once()

    async def test_processes_multiple_calls_in_order_with_a_shared_task_resolution(self):
        message = deepcopy(self.resolve)
        message["tool_calls"].extend(self.facts["tool_calls"])
        self.chat.side_effect = [message, self.done]
        self.call_tool.side_effect = [self.company, {"records": []}]
        result = await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS)
        self.assertEqual(result["tool_call_count"], 2)
        self.assertEqual([item.args[1] for item in self.call_tool.await_args_list],
                         ["resolve_ticker_to_cik", "get_company_facts"])

    async def test_failed_attempts_count_towards_tool_budget(self):
        self.chat.side_effect = [self.facts, self.resolve]
        trace = []
        with self.assertRaisesRegex(RuntimeError, "maximum number of tool calls"):
            await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS, max_tool_calls=1, trace=trace)
        self.call_tool.assert_not_awaited()
        self.assertEqual(sum(event["type"] == "tool" for event in trace), 1)
        self.assertEqual(trace[-1]["status"], "error")

    async def test_multiple_calls_cannot_overrun_budget(self):
        message = deepcopy(self.resolve)
        message["tool_calls"].extend(self.facts["tool_calls"])
        self.chat.return_value = message
        self.call_tool.return_value = self.company
        with self.assertRaisesRegex(RuntimeError, "maximum number of tool calls"):
            await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS, max_tool_calls=1)
        self.call_tool.assert_awaited_once()

    async def test_can_finish_after_using_exact_tool_budget(self):
        self.chat.side_effect = [self.resolve, self.done]
        self.call_tool.return_value = self.company
        result = await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS, max_tool_calls=1)
        self.assertEqual(result["tool_call_count"], 1)

    async def test_step_limit_stops_repeated_tool_requests(self):
        self.chat.return_value = self.resolve
        self.call_tool.return_value = self.company
        trace = []
        with self.assertRaisesRegex(RuntimeError, "maximum number of steps"):
            await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS, max_steps=2, trace=trace)
        self.assertEqual(self.chat.call_count, 2)
        self.assertEqual(self.call_tool.await_count, 1)
        self.assertEqual(trace[-1]["status"], "error")

    async def test_repeated_successful_retrieval_returns_original_evidence_without_another_call(self):
        self.chat.side_effect = [self.resolve, self.facts, self.facts]
        self.call_tool.side_effect = [self.company, {"records": []}]
        result = await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS)
        self.assertEqual(self.call_tool.await_count, 2)
        self.assertEqual(result["tool_call_count"], 2)
        self.assertEqual(result["trace"][-1]["stop_reason"], "repeated_requests")
        evidence = build_agent_evidence(result["trace"])
        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence[-1]["result"], {"records": []})

    async def test_truncated_summary_preserves_collected_evidence_for_writer_review(self):
        self.chat.side_effect = [self.resolve, self.facts, IncompleteResponseError("Output limit")]
        self.call_tool.side_effect = [self.company, {"records": []}]
        config = {"options": {"num_predict": 4096}}
        result = await run_specialist(self.task, config, self.client, TOOL_SCHEMAS)
        self.assertEqual(result["trace"][-1]["stop_reason"], "model_output_limit")
        self.assertEqual(len(build_agent_evidence(result["trace"])), 2)
        self.assertEqual(config["options"]["num_predict"], 4096)
        self.assertEqual(self.chat.call_args.args[1]["options"]["num_predict"], 1024)

    async def test_truncation_without_retrieved_data_still_fails(self):
        self.chat.side_effect = [self.resolve, IncompleteResponseError("Output limit")]
        self.call_tool.return_value = self.company
        with self.assertRaises(IncompleteResponseError):
            await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS)

    async def test_connection_and_model_failures_preserve_trace_and_original_exception(self):
        error = RuntimeError("Disconnected")
        self.chat.return_value = self.resolve
        self.call_tool.side_effect = error
        trace = []
        with self.assertRaises(RuntimeError) as raised:
            await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS, trace=trace)
        self.assertIs(raised.exception, error)
        self.assertEqual(trace[-2]["type"], "tool")
        self.assertEqual(trace[-2]["status"], "error")
        self.assertEqual(build_agent_evidence(trace), [])
        self.chat.side_effect = error
        trace = []
        with self.assertRaises(RuntimeError) as raised:
            await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS, trace=trace)
        self.assertIs(raised.exception, error)
        self.assertEqual(trace[-2]["type"], "model")
        self.assertEqual(trace[-2]["status"], "error")

    async def test_malformed_model_messages_fail_without_executing_tools(self):
        messages = [None, {"role": "tool"}, {"tool_calls": {}}, {"tool_calls": [None]},
                    {"tool_calls": [{"function": {"name": " "}}]}, {"content": " "},
                    model_tool_message("resolve_ticker_to_cik", {"ticker": float("nan")})]
        for message in messages:
            with self.subTest(message=message):
                self.chat.return_value = message
                trace = []
                with self.assertRaises(ValueError):
                    await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS, trace=trace)
                self.assertEqual(trace[-2]["status"], "error")
        self.call_tool.assert_not_awaited()

    async def test_nonfinite_tool_results_are_not_accepted_as_evidence(self):
        self.task["agent"] = "filing_rag"
        self.chat.return_value = model_tool_message("search_filings", {"ticker": "AAPL", "query": "risks"})
        for result in ({"value": float("nan")}, {"value": {1, 2}}, []):
            with self.subTest(result=result):
                self.call_tool.return_value = result
                trace = []
                with self.assertRaises(RuntimeError):
                    await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS, trace=trace)
                self.assertEqual(build_agent_evidence(trace), [])

    async def test_summary_without_tools_does_not_become_evidence(self):
        self.chat.return_value = self.done
        result = await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS)
        self.assertEqual(result["tool_call_count"], 0)
        self.assertEqual(build_agent_evidence(result["trace"]), [])

    async def test_resolution_is_not_shared_between_runs(self):
        self.chat.side_effect = [self.resolve, self.done, self.facts, self.done]
        self.call_tool.return_value = self.company
        await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS)
        second = await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS)
        self.call_tool.assert_awaited_once()
        self.assertEqual(build_agent_evidence(second["trace"]), [])

    async def test_invalid_inputs_are_rejected_before_model_call(self):
        for field in ("max_steps", "max_tool_calls"):
            for value in (True, 0, -1, "2", 1.5):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS, **{field: value})
        for task in (None, {}, {**self.task, "instruction": " "}, {**self.task, "id": " padded"},
                     {**self.task, "agent": "unknown"}):
            with self.subTest(task=task):
                with self.assertRaises(ValueError):
                    await run_specialist(task, {}, self.client, TOOL_SCHEMAS)
        with self.assertRaises(ValueError):
            await run_specialist(self.task, {}, None, TOOL_SCHEMAS)
        with self.assertRaises(ValueError):
            await run_specialist(self.task, {}, self.client, [])
        with self.assertRaises(ValueError):
            await run_specialist(self.task, {}, self.client, TOOL_SCHEMAS, trace=[{}])
        self.chat.assert_not_called()
        self.call_tool.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
