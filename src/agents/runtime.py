import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from mcp import Client, StdioServerParameters

from src.agents.single_agent import run_agent_async
from src.mcp.client import load_mcp_tool_schemas
from src.agents.orchestrator import run_orchestrator
from src.utils.utils import save_json
from src.llm.usage import summarize_usage

TRACE_DIRECTORY = Path(__file__).resolve().parents[2] / "logs" / "runs"


def model_settings(config):
    keys = ("provider", "model", "think", "options", "reasoning_effort", "max_output_tokens")
    settings = {key: config[key] for key in keys if key in config}
    if "roles" in config:
        settings["roles"] = {role: model_settings(value) for role, value in config["roles"].items()}
    return settings


def save_run_trace(question, llm_config, trace, result=None, error=None):
    """Keep local diagnostic evidence without copying credentials or headers."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = TRACE_DIRECTORY / f"{timestamp}_{uuid4().hex[:8]}.json"
    payload = {
        "question": question, "recorded_at": datetime.now(timezone.utc).isoformat(),
        "model_settings": model_settings(llm_config),
        "result": result, "trace": trace,
        "usage": summarize_usage(trace),
        "error": None if error is None else {"type": type(error).__name__, "message": str(error)},
    }
    save_json(payload, path)
    return str(path)


async def run_mcp_agent(question, llm_config, verbose=False, trace=None):
    #Shared MCP execution path for the CLI and evaluation runner.
    project_root = Path(__file__).resolve().parents[2]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp.server"],
        cwd=str(project_root),
        env=dict(os.environ),
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

async def run_mcp_orchestrator(question, llm_config, verbose=False, trace=None):
    project_root = Path(__file__).resolve().parents[2]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m","src.mcp.server"],
        cwd=str(project_root),
        env=dict(os.environ),
    )
    run_trace = [] if trace is None else trace
    result = None
    error = None
    try:
        async with Client(parameters, raise_exceptions=True) as client:
            tool_schemas = await load_mcp_tool_schemas(client)
            if verbose:
                names = [schema["function"]["name"] for schema in tool_schemas]
                print(f"MCP tools: {', '.join(names)}", file=sys.stderr)
            result = await run_orchestrator(
                question, llm_config, mcp_client=client,
                tool_schemas=tool_schemas, trace=run_trace,
            )
            result["usage"] = summarize_usage(run_trace)
            return result
    except Exception as caught:
        error = caught
        raise
    finally:
        try:
            trace_path = save_run_trace(question, llm_config, run_trace, result, error)
            if result is not None:
                result["trace_path"] = trace_path
            elif error is not None:
                error.add_note(f"Diagnostic trace: {trace_path}")
        except (OSError, TypeError, ValueError) as trace_error:
            # A logging failure must not discard the original result or error.
            if result is not None:
                result["trace_error"] = str(trace_error)
            elif error is not None:
                error.add_note(f"Diagnostic trace could not be saved: {trace_error}")
