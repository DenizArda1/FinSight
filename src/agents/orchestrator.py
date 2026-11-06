import asyncio
from copy import deepcopy
from time import perf_counter

from src.agents.agent_states import AgentState, create_initial_state
from src.agents.critic import run_critic
from src.agents.planner import generate_plan
from src.agents.specialist import run_specialist
from src.agents.writer import run_writer


async def run_orchestrator(question, llm_config, mcp_client, tool_schemas, trace=None, max_revisions=2) -> AgentState:
    if type(max_revisions) is not int or not 0 <= max_revisions <= 2:
        raise ValueError("Max revisions must be an integer between 0 and 2")
    state = create_initial_state(question)
    if trace is not None:
        if not isinstance(trace, list) or trace:
            raise ValueError("Trace must be an empty list for a new run")
        state["trace"] = trace

    planner_started = perf_counter()
    planner_usage = {}
    state["trace"].append({"type": "agent", "agent": "planner", "status": "started"})
    try:
        plan = await asyncio.to_thread(generate_plan, state["question"], llm_config, telemetry=planner_usage)
    except Exception as error:
        state["trace"].append({
            "type": "agent", "agent": "planner", "status": "error",
            "error": {"type": type(error).__name__, "message": str(error)},
            "elapsed_seconds": perf_counter() - planner_started,
            **planner_usage,
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
        **planner_usage,
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

    feedback = None
    last_candidate = None
    for revision in range(max_revisions + 1):
        state["revision_count"] = revision
        writer_response = None
        try:
            await run_writer(state, llm_config, feedback=feedback)
        except ValueError as error:
            event = state["trace"][-1]
            if event.get("agent") != "writer" or event.get("stage") not in {"parse", "schema", "deterministic"}:
                raise
            writer_response = state["trace"][-2].get("content")
            state["verification"] = {
                "status": "failed", "supported": False, "issues": [str(error)],
                "stage": "writer_validation", "deterministic_fields": "failed",
                "method": "source_fields_and_llm_judge",
            }
        else:
            last_candidate = {key: deepcopy(state[key]) for key in ("draft", "composition", "evidence")}
            await run_critic(state, llm_config)
        verification = state["verification"]
        if verification["status"] in {"passed", "error"}:
            return state

        if revision == max_revisions:
            if state["draft"] is None and last_candidate is not None:
                state.update(last_candidate)
                # Keep the failed verification and answer=None: this is only an
                # explicitly unverified partial draft, never a successful answer.
                state["verification"]["issues"].append(
                    "The last revision could not be rendered; the earlier unverified draft is retained."
                )
            state["trace"].append({
                "type": "revision", "status": "exhausted",
                "revision_count": revision, "max_revisions": max_revisions,
                "issues": deepcopy(verification["issues"]),
            })
            return state

        feedback = {
            "previous_draft": state["draft"],
            "previous_composition": deepcopy(state["composition"]),
            "issues": deepcopy(verification["issues"]),
        }
        if writer_response is not None:
            feedback["previous_response"] = writer_response
        state["trace"].append({
            "type": "revision", "status": "scheduled",
            "revision_count": revision + 1, "max_revisions": max_revisions,
            "issues": deepcopy(verification["issues"]),
        })

    return state
