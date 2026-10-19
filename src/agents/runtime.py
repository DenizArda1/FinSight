import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

from src.agents.single_agent import run_agent_async
from src.mcp.client import load_mcp_tool_schemas


async def run_mcp_agent(question, llm_config, verbose=False, trace=None):
    """Shared MCP execution path for the CLI and evaluation runner."""
    project_root = Path(__file__).resolve().parents[2]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp.server"],
        cwd=str(project_root),
    )
    async with Client(parameters, raise_exceptions=True) as client:
        tool_schemas = await load_mcp_tool_schemas(client)
        if verbose:
            names = [schema["function"]["name"] for schema in tool_schemas]
            print(f"MCP tools: {', '.join(names)}", file=sys.stderr)
        return await run_agent_async(
            question, llm_config, verbose=verbose, return_details=True,
            trace=trace, mcp_client=client, tool_schemas=tool_schemas,
        )
