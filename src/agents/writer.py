import asyncio
import json
from copy import deepcopy
from time import perf_counter

from jsonschema import Draft202012Validator, ValidationError

from src.agents.agent_states import AgentState
from src.agents.revisions import apply_paragraph_patches, numbered_paragraphs, patch_schema
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
        messages = build_agent_answer_messages(
            state["question"], state["evidence"], catalog, feedback=feedback,
            request_type=state["request_type"],
        )
        schema = composition_schema(catalog, request_type=state["request_type"], evidence=state["evidence"])
        if state["request_type"] == "out_of_scope":
            schema["properties"]["kind"]["enum"] = ["refusal"]
            schema["properties"]["facts"]["maxItems"] = 0
        response_schema = schema
        targets = feedback.get("repair_targets") if feedback else None
        if targets:
            previous = feedback.get("previous_composition")
            if not isinstance(previous, dict):
                raise ValueError("Paragraph revision requires the previous composition")
            response_schema = patch_schema(targets)
            messages[0]["content"] += (
                " REVISION OUTPUT OVERRIDE: return only {patches: [{paragraph_id, text}]}, "
                "not kind/text/facts. Replace exactly the selected paragraphs, each with a single "
                "non-empty paragraph. Keep exact field placeholders and source citations. "
                "The application preserves all other paragraphs, kind and facts."
            )
            messages[-1] = {"role": "user", "content": json.dumps({
                "instruction": "Correct only repair_targets; return paragraph patches, not a complete answer.",
                "question": state["question"],
                "paragraphs": numbered_paragraphs(previous["text"]),
                "repair_targets": targets,
            }, ensure_ascii=False, allow_nan=False)}
        stage = "composition"
        text = await asyncio.to_thread(
            request_answer_check, messages, llm_config, state["trace"], "writer", response_schema,
        )
        stage = "parse"
        composition = json.loads(text)
        stage = "schema"

        try:
            if targets:
                composition = apply_paragraph_patches(previous, targets, composition)
            Draft202012Validator(schema).validate(composition)
        except ValidationError as error:
            raise ValueError(f"Invalid writer response: {error.message}") from error

        stage = "deterministic"
        template = compose_template(composition, catalog, request_type=state["request_type"])
        draft = render_agent_template(template, state["evidence"])
        state["composition"] = composition
        state["draft"] = draft
        
    except Exception as error:
        event = {
            "type": "agent", "agent": "writer", "status": "error", "stage": stage,
            "error": {"type": type(error).__name__, "message": str(error)},
            "elapsed_seconds": perf_counter() - started,
        }
        state["trace"].append(event)
        raise

    state["trace"].append({
        "type": "agent", "agent": "writer", "status": "completed",
        "elapsed_seconds": perf_counter() - started,
    })
    return state
