import asyncio
import json
from copy import deepcopy

from mcp import types
from mcp.server import Server
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.stdio import stdio_server

from src.tools.agentic_tools import TOOL_SCHEMAS
from src.tools.dispatcher import execute_tool


def execute_mcp_tool(name: str, arguments: dict) -> dict:
    # Validate the original JSON arguments before any function-signature coercion.
    try:
        return execute_tool(name, arguments, prepare=True)
    except (ValueError, TypeError, OSError) as error:
        raise ToolError(str(error)) from error


async def list_tools(context, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[
        types.Tool(
            name=schema["function"]["name"],
            description=schema["function"]["description"],
            input_schema=deepcopy(schema["function"]["parameters"]),
            output_schema={"type": "object"},
        )
        for schema in TOOL_SCHEMAS
    ])


async def call_tool(context, params) -> types.CallToolResult:
    arguments = {} if params.arguments is None else params.arguments
    try:
        result = await asyncio.to_thread(execute_mcp_tool, params.name, arguments)
    except ToolError as error:
        return types.CallToolResult(
            is_error=True,
            content=[types.TextContent(type="text", text=str(error))],
        )
    return types.CallToolResult(
        structured_content=result,
        content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, allow_nan=False))],
    )


server = Server("FinSight", on_list_tools=list_tools, on_call_tool=call_tool)


async def run_stdio() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
