import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from mcp import Client, StdioServerParameters
from mcp.server.mcpserver.exceptions import ToolError

from src.mcp.client import MCPToolError, call_mcp_tool, load_mcp_tool_schemas
from src.mcp.server import execute_mcp_tool, server
from src.tools.agentic_tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
from src.tools.dispatcher import execute_tool


class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_advertised_schemas_exactly_match_direct_contracts(self):
        async with Client(server) as client:
            self.assertEqual(await load_mcp_tool_schemas(client), TOOL_SCHEMAS)

    async def test_raw_invalid_arguments_are_rejected_before_function_execution(self):
        function = Mock(return_value={})
        cases = [
            ("get_company_facts", {"cik": "0000320193", "concept": "revenue", **extra})
            for extra in ({"years": True}, {"years": "1"}, {"years": 0}, {"years": 6},
                          {"years": 1.5}, {"unknown": 1}, {"concept": "sales"}, {"unit": "EUR"})
        ]
        cases.extend([
            ("resolve_ticker_to_cik", {"ticker": 123}),
            ("search_filings", {"ticker": "AAPL", "query": "Risk", "fiscal_year": True}),
            ("compute_metrics", {"cik": "0000320193", "metrics": ["net_margin", "net_margin"]}),
            ("get_filing_section", {"ticker": "AAPL", "year": "2025", "section": "Item 1A"}),
        ])
        with patch.dict(TOOL_FUNCTIONS, {name: function for name in TOOL_FUNCTIONS}):
            async with Client(server) as client:
                for name, arguments in cases:
                    with self.subTest(name=name, arguments=arguments):
                        with self.assertRaisesRegex(ValueError, "Invalid arguments"):
                            execute_tool(name, arguments)
                        with self.assertRaisesRegex(MCPToolError, "Invalid arguments"):
                            await call_mcp_tool(client, name, arguments)
        function.assert_not_called()

    async def test_stdio_preserves_types_and_extra_fields_until_validation(self):
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "src.mcp.server"],
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        async with Client(parameters) as client:
            for extra in ({"years": True}, {"years": "1"}, {"unknown": 1}):
                with self.subTest(extra=extra), self.assertRaisesRegex(MCPToolError, "Invalid arguments"):
                    await call_mcp_tool(client, "get_company_facts", {
                        "cik": "0000000000", "concept": "revenue", **extra,
                    })

    @patch("src.mcp.server.execute_tool")
    async def test_expected_error_is_readable_and_same_connection_can_retry(self, execute):
        payload = {"company": {"cik": "0000320193"}, "records": []}
        execute.side_effect = [ValueError("Unknown concept: sales"), payload]

        async with Client(server, raise_exceptions=True) as client:
            with self.assertRaisesRegex(MCPToolError, "Unknown concept: sales"):
                await call_mcp_tool(client, "get_company_facts", {
                    "cik": "0000320193", "concept": "sales",
                })
            result = await call_mcp_tool(client, "get_company_facts", {
                "cik": "0000320193", "concept": "revenue",
            })

        self.assertEqual(result, payload)
        self.assertEqual(execute.call_count, 2)

    @patch("src.mcp.server.execute_tool")
    async def test_adapter_only_translates_expected_errors(self, execute):
        for failure in (ValueError("Invalid input"), TypeError("Invalid type"), FileNotFoundError("Missing data")):
            with self.subTest(failure=failure):
                execute.side_effect = failure
                with self.assertRaises(ToolError) as raised:
                    execute_mcp_tool("get_company_facts", {})
                self.assertEqual(str(raised.exception), str(failure))
                self.assertIs(raised.exception.__cause__, failure)

        failure = RuntimeError("Unexpected internal failure")
        execute.side_effect = failure
        with self.assertRaises(RuntimeError) as raised:
            execute_mcp_tool("get_company_facts", {})
        self.assertIs(raised.exception, failure)


if __name__ == "__main__":
    unittest.main()
