import asyncio
from copy import deepcopy
from time import perf_counter

from src.agents.agent_states import AgentState, create_initial_state
from src.agents.critic import run_critic
from src.agents.planner import generate_plan
from src.agents.specialist import SpecialistLimitError, run_specialist
from src.agents.writer import run_writer
from src.agents.coverage import check_coverage
from src.observability import observation, update_observation


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
        with observation("planner", "agent"):
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

    financial_years = max((task.get('years', 1) for task in state['plan']
                           if task['agent'] == 'financial_data'), default=1)
    for task_number, task in enumerate(state["plan"], 1):
        task_trace = []
        try:
            try:
                scoped_task = dict(task)
                if task['agent'] == 'financial_data':
                    scoped_task['years'] = financial_years
                with observation(task["agent"], "agent", metadata={"task_number": task_number}):
                    result = await run_specialist(scoped_task, llm_config, mcp_client, tool_schemas, trace=task_trace)
            except SpecialistLimitError:
                result = {
                    "task_id": task["id"], "agent": task["agent"],
                    "summary": "Retrieval budget exhausted. Coverage is incomplete; use only collected tool evidence.",
                    "trace": deepcopy(task_trace), "incomplete": True,
                }
                task_trace.append({
                    "type": "coverage", "task_id": task["id"], "agent": task["agent"],
                    "status": "incomplete", "reason": "retrieval_budget_exhausted",
                    "instruction": task["instruction"],
                })
            if task["agent"] == "financial_data":
                state["financial_results"].append(result)
            elif task["agent"] == "filing_rag":
                state["filing_results"].append(result)
        finally:
            state["trace"].extend(deepcopy(task_trace))

    if state['request_type'] not in {'clarification', 'out_of_scope'}:
        with observation("coverage", "chain"):
            coverage = await check_coverage(state, llm_config)
        repair_tasks = coverage['tasks']
        for index, task in enumerate(repair_tasks, 1):
            repair_trace = []
            scoped_task = {**task, 'id': f'coverage_repair_{index}'}
            try:
                with observation(task["agent"], "agent", metadata={"task_id": scoped_task["id"]}):
                    await run_specialist(scoped_task, llm_config, mcp_client, tool_schemas,
                                         trace=repair_trace, max_steps=6, max_tool_calls=6)
            except SpecialistLimitError:
                pass  # The bounded pass still retains any successful tool evidence.
            finally:
                state['trace'].extend(deepcopy(repair_trace))
        if repair_tasks:
            with observation("coverage", "chain"):
                coverage = await check_coverage(state, llm_config)
        state['coverage'] = {key: value for key, value in coverage.items() if key != 'tasks'}
        state['coverage']['repair_tasks_attempted'] = len(repair_tasks)
        state['trace'].append({'type': 'coverage', **state['coverage']})

    feedback = None
    last_candidate = None
    critic_reviews = 0
    # Syntax repairs can consume the normal budget before the first content
    # review. Reserve at most one further revision for that first review.
    for revision in range(max_revisions + 2):
        state["revision_count"] = revision
        writer_response = None
        try:
            with observation("writer", "agent", metadata={"revision": revision}):
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
            with observation("critic", "agent", metadata={"revision": revision}) as span:
                await run_critic(state, llm_config)
                status = (state["verification"] or {}).get("status")
                update_observation(span, metadata={
                    "revision": revision,
                    "verification_status": status,
                }, level="ERROR" if status == "error" else None)
            critic_reviews += 1
        verification = state["verification"]
        if verification["status"] in {"passed", "error"}:
            return state

        first_content_repair = (max_revisions > 0 and revision == max_revisions
                                and critic_reviews == 1 and writer_response is None)
        if revision >= max_revisions and not first_content_repair:
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
            "reserved_content_repair": first_content_repair,
            "issues": deepcopy(verification["issues"]),
        })

    return state
