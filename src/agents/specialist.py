from src.mcp.client import call_mcp_tool
from src.tools.agentic_tools import AGENT_TOOL_NAMES


async def execute_specialist_tool(agent_name, tool_name, arguments, mcp_client, resolved_ciks):
    
    if not isinstance(agent_name, str) or agent_name not in AGENT_TOOL_NAMES:
        raise ValueError(f"Unknown agent: {agent_name}")
    if not isinstance(tool_name, str) or tool_name not in AGENT_TOOL_NAMES[agent_name]:
        raise ValueError(f"Tool {tool_name!r} is not allowed for {agent_name}")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary")
    if not isinstance(resolved_ciks, set):
        raise ValueError("Resolved CIKs must be a set")

    if tool_name in {"get_company_facts", "compute_metrics"}:
        cik = arguments.get("cik")
        if not isinstance(cik, str) or cik not in resolved_ciks:
            raise ValueError(
                "Resolve the ticker with resolve_ticker_to_cik before requesting financial data. "
                "The CIK must match a successful company resolution in this task."
            )

    result = await call_mcp_tool(mcp_client, tool_name, arguments)

    if tool_name == "resolve_ticker_to_cik":
        cik = result.get("cik")
        if not isinstance(cik, str) or not cik.strip():
            raise ValueError("Company resolution must return a non-empty CIK string")
        resolved_ciks.add(cik)

    return result
