import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

from src.mcp.client import MCPToolError, call_mcp_tool, load_mcp_tool_schemas


class MCPClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovers_all_pages_and_preserves_schema_constraints(self):
        parameters = {
            "type": "object", "properties": {"years": {"type": "integer", "minimum": 1}},
            "required": ["years"], "additionalProperties": False,
        }
        client = SimpleNamespace(list_tools=AsyncMock(side_effect=[
            SimpleNamespace(tools=[SimpleNamespace(
                name="first_tool", description="First description", input_schema=parameters,
            )], next_cursor="page-two"),
            SimpleNamespace(tools=[SimpleNamespace(
                name="second_tool", description=None, input_schema={"type": "object"},
            )], next_cursor=None),
        ]))

        schemas = await load_mcp_tool_schemas(client)

        self.assertEqual(client.list_tools.await_args_list, [call(cursor=None), call(cursor="page-two")])
        self.assertEqual(schemas, [
            {"type": "function", "function": {
                "name": "first_tool", "description": "First description", "parameters": parameters,
            }},
            {"type": "function", "function": {
                "name": "second_tool", "description": "", "parameters": {"type": "object"},
            }},
        ])

    async def test_empty_tool_directory_is_rejected(self):
        client = SimpleNamespace(list_tools=AsyncMock(return_value=SimpleNamespace(
            tools=[], next_cursor=None,
        )))

        with self.assertRaisesRegex(ValueError, "did not expose any tools"):
            await load_mcp_tool_schemas(client)

    async def test_preserves_records_and_source_metadata(self):
        payload = {
            "records": [{"value": 123, "source_url": "https://example.com/filing"}],
            "missing_period_ends": [],
        }
        client = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(
            is_error=False, structured_content=payload,
        )))
        arguments = {"cik": "0000320193", "concept": "revenue"}

        result = await call_mcp_tool(client, "get_company_facts", arguments)

        self.assertEqual(result, payload)
        client.call_tool.assert_awaited_once_with("get_company_facts", arguments)

    async def test_error_result_is_rejected_even_with_structured_content(self):
        client = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(
            is_error=True,
            content=[SimpleNamespace(type="text", text="Unknown ticker")],
            structured_content={"ticker": "INVALID"},
        )))

        with self.assertRaisesRegex(MCPToolError, "resolve_ticker_to_cik.*Unknown ticker"):
            await call_mcp_tool(client, "resolve_ticker_to_cik", {"ticker": "INVALID"})

    async def test_error_without_text_has_fallback_message(self):
        client = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(
            is_error=True, content=[], structured_content=None,
        )))

        with self.assertRaisesRegex(MCPToolError, "Unknown error"):
            await call_mcp_tool(client, "search_filings", {})

    async def test_rejects_missing_or_non_object_structured_content(self):
        for payload in (None, [], "plain text"):
            with self.subTest(payload=payload):
                client = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(
                    is_error=False, structured_content=payload,
                )))

                with self.assertRaisesRegex(RuntimeError, "structured object") as raised:
                    await call_mcp_tool(client, "get_company_facts", {})
                self.assertNotIsInstance(raised.exception, MCPToolError)

    async def test_connection_failure_is_not_converted_to_a_tool_error(self):
        failure = ConnectionError("MCP connection closed")
        client = SimpleNamespace(call_tool=AsyncMock(side_effect=failure))

        with self.assertRaises(ConnectionError) as raised:
            await call_mcp_tool(client, "resolve_ticker_to_cik", {"ticker": "AAPL"})

        self.assertIs(raised.exception, failure)


if __name__ == "__main__":
    unittest.main()
