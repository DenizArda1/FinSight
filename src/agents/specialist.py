import asyncio
import json
from copy import deepcopy
from time import perf_counter

from src.llm.client import send_chat_request
from src.llm.prompts import build_specialist_messages
from src.mcp.client import MCPToolError, call_mcp_tool
from src.tools.agentic_tools import AGENT_TOOL_NAMES, get_agent_tool_schemas


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

async def run_specialist(task, llm_config, mcp_client, tool_schemas,max_steps=6, max_tool_calls=10, trace=None):
    """Collect tool evidence for one task without composing a final answer.

    An optional empty trace list lets the caller retain records if execution fails.
    A returned summary is model output, not verified evidence.
    """
    if not isinstance(task, dict):
        raise ValueError("Task must be a dictionary")
    for field in ("id", "agent", "instruction"):
        if not isinstance(task.get(field), str) or not task[field].strip():
            raise ValueError(f"Task {field} must be a non-empty string")
    if task["id"] != task["id"].strip():
        raise ValueError("Task IDs must not contain leading or trailing whitespace")
    if type(max_steps) is not int or max_steps <= 0:
        raise ValueError("Max steps must be a positive integer")
    if type(max_tool_calls) is not int or max_tool_calls <= 0:
        raise ValueError("Max tool calls must be a positive integer")
    if mcp_client is None:
        raise ValueError("An MCP client is required")
    if trace is None:
        trace = []
    if not isinstance(trace, list) or trace:
        raise ValueError("Trace must be an empty list for a new task")

    available_tools = get_agent_tool_schemas(task["agent"], tool_schemas)
    messages = build_specialist_messages(deepcopy(task))
    identity = {"task_id": task["id"], "agent": task["agent"]}
    resolved_ciks = set()
    tool_call_count = 0
    started = perf_counter()
    trace.append({"type": "agent", **identity, "status": "started"})

    try:
        for step in range(1, max_steps + 1):
            model_started = perf_counter()
            model_event = {"type": "model", **identity, "step": step}
            try:
                message = await asyncio.to_thread(
                    send_chat_request, messages, llm_config, tools=available_tools,
                )

                if not isinstance(message, dict):
                    raise ValueError("Model response must be a message object")
                if message.get("role", "assistant") != "assistant":
                    raise ValueError("Model message role must be assistant")

                tool_calls = message.get("tool_calls", [])
                if not isinstance(tool_calls, list):
                    raise ValueError("Tool calls must be a list")

                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict) or not isinstance(tool_call.get("function"), dict):
                        raise ValueError("Each tool call must contain a function object")

                    name = tool_call["function"].get("name")
                    if not isinstance(name, str) or not name.strip():
                        raise ValueError("Tool call names must be non-empty strings")

                json.dumps(tool_calls, allow_nan=False)
                if not tool_calls:
                    content = message.get("content")
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError("Specialist summary must be a non-empty string")
                        
            except Exception as error:
                model_event.update({
                    "status": "error",
                    "error": {"type": type(error).__name__, "message": str(error)},
                    "elapsed_seconds": perf_counter() - model_started,
                })
                trace.append(model_event)
                raise

            model_event.update({
                "status": "completed", "tool_calls": deepcopy(tool_calls),
                "elapsed_seconds": perf_counter() - model_started,
            })
            trace.append(model_event)
            # Keep the assistant message for tool round trips; do not persist thinking.
            messages.append(deepcopy(message))

            if not tool_calls:
                trace.append({
                    "type": "agent", **identity, "status": "completed",
                    "elapsed_seconds": perf_counter() - started,
                })
                return {
                    **identity, "summary": content, "trace": deepcopy(trace),
                    "tool_call_count": tool_call_count,
                }

            for tool_call in tool_calls:
                if tool_call_count >= max_tool_calls:
                    raise RuntimeError("Specialist reached the maximum number of tool calls")
                tool_call_count += 1
                function = tool_call["function"]
                name, arguments = function["name"], function.get("arguments")
                tool_started = perf_counter()
                event = {
                    "type": "tool", **identity, "step": step,
                    "call_id": tool_call_count, "name": name,
                    "arguments": deepcopy(arguments),
                }
                try:
                    result = await execute_specialist_tool(
                        task["agent"], name, arguments, mcp_client, resolved_ciks,
                    )
                    if not isinstance(result, dict):
                        raise RuntimeError("Tool result must be a structured object")
                    try:
                        json.dumps(result, ensure_ascii=False, allow_nan=False)
                    except (ValueError, TypeError) as error:
                        raise RuntimeError("Tool result must contain valid finite JSON data") from error
                    event["status"] = "completed"
                except Exception as error:
                    result = {"error": {"type": type(error).__name__, "message": str(error)}}
                    event["status"] = "error"
                    if not isinstance(error, (ValueError, MCPToolError)):
                        event.update({
                            "result": deepcopy(result),
                            "elapsed_seconds": perf_counter() - tool_started,
                        })
                        trace.append(event)
                        raise
                event.update({
                    "result": deepcopy(result),
                    "elapsed_seconds": perf_counter() - tool_started,
                })
                trace.append(event)
                messages.append({
                    "role": "tool", "tool_name": name,
                    "content": json.dumps(result, ensure_ascii=False, allow_nan=False),
                })

        raise RuntimeError("Specialist reached the maximum number of steps")
    except Exception as error:
        trace.append({
            "type": "agent", **identity, "status": "error",
            "error": {"type": type(error).__name__, "message": str(error)},
            "elapsed_seconds": perf_counter() - started,
        })
        raise
