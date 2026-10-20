import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, call, patch

from src.agents.specialist import execute_specialist_tool
from src.mcp.client import MCPToolError


class SpecialistToolTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
