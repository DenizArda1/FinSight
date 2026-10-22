import asyncio
import json
from copy import deepcopy
from time import perf_counter

from jsonschema import Draft202012Validator, ValidationError

from src.agents.agent_states import AgentState
from src.llm.prompts import build_agent_answer_messages
from src.verification.agent_answer import (
    build_fact_catalog,
    build_agent_evidence,
    render_agent_template,
    compose_template,
    composition_schema,
    request_answer_check,
)


async def run_writer(state: AgentState, llm_config, feedback=None) -> AgentState:

    state["draft"] = None
    state["answer"] = None
    state["composition"] = None
    state["verification"] = None
    state["evidence"] = []

    started = perf_counter()
    state["trace"].append({"type": "agent", "agent": "writer", "status": "started"})

    stage = "prepare"
    try:
        state["evidence"] = deepcopy(build_agent_evidence(state["trace"]))
        catalog = build_fact_catalog(state["evidence"])
        messages = build_agent_answer_messages(state["question"], state["evidence"], catalog, feedback=feedback)
        schema = composition_schema(catalog)

        stage = "composition"
        text = await asyncio.to_thread(
            request_answer_check, messages, llm_config, state["trace"], "writer", schema,
        )
        stage = "parse"
        composition = json.loads(text)
        stage = "schema"

        try:
            Draft202012Validator(schema).validate(composition)
        except ValidationError as error:
            raise ValueError(f"Invalid writer response: {error.message}") from error

        stage = "deterministic"
        template = compose_template(composition, catalog)
        draft = render_agent_template(template, state["evidence"])
        state["composition"] = composition
        state["draft"] = draft
        
    except Exception as error:
        state["trace"].append({
            "type": "agent", "agent": "writer", "status": "error", "stage": stage,
            "error": {"type": type(error).__name__, "message": str(error)},
            "elapsed_seconds": perf_counter() - started,
        })
        raise

    state["trace"].append({
        "type": "agent", "agent": "writer", "status": "completed",
        "elapsed_seconds": perf_counter() - started,
    })
    return state
