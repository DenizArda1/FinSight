import asyncio
import json
from copy import deepcopy
from time import perf_counter

from src.llm.client import IncompleteResponseError, send_chat_request
from src.llm.prompts import build_specialist_messages
from src.mcp.client import MCPToolError, call_mcp_tool
from src.tools.agentic_tools import AGENT_TOOL_NAMES, get_agent_tool_schemas
from src.verification.evidence import REPORT_SEARCH_TOOLS, MAX_REPORT_SOURCE_CHARS, limit_report_evidence, evidence_for_prompt


async def execute_specialist_tool(agent_name, tool_name, arguments, mcp_client, resolved_ciks,
                                  requested_fiscal_year=None):
    
    if not isinstance(agent_name, str) or agent_name not in AGENT_TOOL_NAMES:
        raise ValueError(f"Unknown agent: {agent_name}")
    if not isinstance(tool_name, str) or tool_name not in AGENT_TOOL_NAMES[agent_name]:
        raise ValueError(f"Tool {tool_name!r} is not allowed for {agent_name}")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary")
    if not isinstance(resolved_ciks, set):
        raise ValueError("Resolved CIKs must be a set")
    if requested_fiscal_year is not None:
        if type(requested_fiscal_year) is not int or requested_fiscal_year <= 0:
            raise ValueError("Requested fiscal year must be a positive integer or null")
        if tool_name in {"search_company_updates", "search_fed_releases", "get_bls_series"}:
            raise ValueError("Recent supplemental sources cannot satisfy an explicit historical fiscal-year task.")
        if tool_name == "search_filings":
            if (arguments.get("latest", False) is not False
                    or type(arguments.get("fiscal_year")) is not int
                    or arguments["fiscal_year"] != requested_fiscal_year):
                raise ValueError(
                    f"This task requires FY{requested_fiscal_year}. Call search_filings with "
                    f"fiscal_year={requested_fiscal_year} and omit latest or set it to false. "
                    "Do not substitute the latest report for the requested year."
                )
        elif tool_name == "get_filing_section":
            if type(arguments.get("year")) is not int or arguments["year"] != requested_fiscal_year:
                raise ValueError(f"This task requires get_filing_section with year={requested_fiscal_year}.")

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
    fiscal_year = task.get("fiscal_year")
    if fiscal_year is not None and (type(fiscal_year) is not int or fiscal_year <= 0):
        raise ValueError("Task fiscal_year must be a positive integer or null")
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
    searched_sections = set()
    successful_calls = set()
    has_research_result = False
    started = perf_counter()
    trace.append({"type": "agent", **identity, "status": "started"})
    # Tool arguments and a short retrieval summary do not need a long generation.
    model_config = deepcopy(llm_config)
    options = model_config.setdefault("options", {})
    requested_limit = options.get("num_predict", 1024)
    if type(requested_limit) is int and requested_limit > 0:
        options["num_predict"] = min(requested_limit, 1024)
    else:
        options["num_predict"] = 1024

    try:
        for step in range(1, max_steps + 1):
            model_started = perf_counter()
            model_event = {"type": "model", **identity, "step": step,
                           "max_output_tokens": options["num_predict"]}
            try:
                step_tools = available_tools
                if task["agent"] == "financial_data" and not resolved_ciks:
                    step_tools = [tool for tool in available_tools
                                  if tool["function"]["name"] not in {"get_company_facts", "compute_metrics"}]
                message = await asyncio.to_thread(
                    send_chat_request, messages, model_config, tools=step_tools, telemetry=model_event,
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
                if isinstance(error, IncompleteResponseError) and has_research_result:
                    trace.append({
                        "type": "agent", **identity, "status": "completed",
                        "stop_reason": "model_output_limit",
                        "elapsed_seconds": perf_counter() - started,
                    })
                    return {
                        **identity,
                        "summary": "Retrieval stopped at the model output limit. Collected evidence may be partial; assess coverage and limitations.",
                        "trace": deepcopy(trace), "tool_call_count": tool_call_count,
                    }
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

            pending_calls = [(tool_call, "model") for tool_call in tool_calls]
            new_calls = 0
            for tool_call, origin in pending_calls:
                function = tool_call["function"]
                name, arguments = function["name"], function.get("arguments")
                call_key = json.dumps([name, arguments], sort_keys=True, allow_nan=False)
                if call_key in successful_calls:
                    messages.append({
                        "role": "tool", "tool_name": name,
                        "content": "This exact request already succeeded. Use its earlier result; empty records are a data limitation. Do not repeat it.",
                    })
                    continue
                if tool_call_count >= max_tool_calls:
                    raise RuntimeError("Specialist reached the maximum number of tool calls")
                tool_call_count += 1
                new_calls += 1
                if origin != "model":
                    messages.append({"role": "assistant", "content": "", "tool_calls": [deepcopy(tool_call)]})
                tool_started = perf_counter()
                event = {
                    "type": "tool", **identity, "step": step,
                    "call_id": tool_call_count, "name": name,
                    "arguments": deepcopy(arguments),
                }
                if origin != "model":
                    event["origin"] = origin
                try:
                    result = await execute_specialist_tool(
                        task["agent"], name, arguments, mcp_client, resolved_ciks,
                        requested_fiscal_year=fiscal_year,
                    )
                    if not isinstance(result, dict):
                        raise RuntimeError("Tool result must be a structured object")
                    try:
                        json.dumps(result, ensure_ascii=False, allow_nan=False)
                    except (ValueError, TypeError) as error:
                        raise RuntimeError("Tool result must contain valid finite JSON data") from error
                    event["status"] = "completed"
                    successful_calls.add(call_key)
                    if name != "resolve_ticker_to_cik":
                        has_research_result = True
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
                model_result = result
                if (event["status"] == "completed" and name == "get_filing_section"
                        and isinstance(result.get("text"), str)
                        and len(result["text"]) > MAX_REPORT_SOURCE_CHARS):
                    bounded = limit_report_evidence([{"source_id": 1, "tool": name, "result": result}])[0]
                    model_result = {**bounded["result"], "metadata": deepcopy(result.get("metadata", {})),
                                    "next_action": "Use the following section-scoped search excerpts for this task. The full section remains in the tool trace."}
                    scope = (arguments["ticker"], arguments["year"], arguments["section"])
                    if scope not in searched_sections:
                        searched_sections.add(scope)
                        pending_calls.append(({"function": {"name": "search_filings", "arguments": {
                            "ticker": arguments["ticker"], "fiscal_year": arguments["year"],
                            "section": arguments["section"], "query": task["instruction"], "top_k": 3,
                        }}}, "section_context_fallback"))
                if event["status"] == "completed" and name in REPORT_SEARCH_TOOLS | {"get_filing_section"}:
                    model_result = evidence_for_prompt([{"source_id": 1, "tool": name, "result": model_result}])[0]["result"]
                messages.append({
                    "role": "tool", "tool_name": name,
                    "content": json.dumps(model_result, ensure_ascii=False, allow_nan=False),
                })

            if new_calls == 0 and has_research_result:
                trace.append({
                    "type": "agent", **identity, "status": "completed",
                    "stop_reason": "repeated_requests",
                    "elapsed_seconds": perf_counter() - started,
                })
                return {
                    **identity,
                    "summary": "Repeated requests stopped. Assess the collected tool evidence for coverage and missing data.",
                    "trace": deepcopy(trace), "tool_call_count": tool_call_count,
                }

        raise RuntimeError("Specialist reached the maximum number of steps")
    except Exception as error:
        trace.append({
            "type": "agent", **identity, "status": "error",
            "error": {"type": type(error).__name__, "message": str(error)},
            "elapsed_seconds": perf_counter() - started,
        })
        raise
