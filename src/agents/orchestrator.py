import asyncio
from copy import deepcopy
from time import perf_counter

from src.agents.agent_states import AgentState, create_initial_state
from src.agents.planner import generate_plan
from src.agents.specialist import run_specialist


async def run_orchestrator(question, llm_config, mcp_client, tool_schemas, trace=None) -> AgentState:
    state = create_initial_state(question)
    if trace is not None:
        if not isinstance(trace, list) or trace:
            raise ValueError("Trace must be an empty list for a new run")
        state["trace"] = trace

    planner_started = perf_counter()
    state["trace"].append({"type": "agent", "agent": "planner", "status": "started"})
    try:
        plan = await asyncio.to_thread(generate_plan, state["question"], llm_config)
    except Exception as error:
        state["trace"].append({
            "type": "agent", "agent": "planner", "status": "error",
            "error": {"type": type(error).__name__, "message": str(error)},
            "elapsed_seconds": perf_counter() - planner_started,
        })
        raise

    state["request_type"] = plan["request_type"]
    state["plan"] = deepcopy(plan["tasks"])

    state["trace"].append({
        "type": "agent",
        "agent": "planner",
        "status": "completed",
        "request_type": plan["request_type"],
        "plan": deepcopy(plan["tasks"]),
        "elapsed_seconds": perf_counter() - planner_started,
    })

    for task in state["plan"]:
        task_trace = []
        try:
            result = await run_specialist(task, llm_config, mcp_client, tool_schemas, trace=task_trace)
            if task["agent"] == "financial_data":
                state["financial_results"].append(result)
            elif task["agent"] == "filing_rag":
                state["filing_results"].append(result)
        finally:
            state["trace"].extend(deepcopy(task_trace))

    return state
