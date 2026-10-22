import json
import asyncio
from copy import deepcopy
from time import perf_counter

from jsonschema import Draft202012Validator, ValidationError

from src.agents.agent_states import AgentState
from src.llm.prompts import build_agent_verification_messages
from src.verification.agent_answer import (
    build_agent_evidence,
    build_fact_catalog,
    compose_template,
    composition_schema,
    render_agent_template,
    request_answer_check,
    parse_agent_verdict,
    VERIFICATION_SCHEMA,
)


async def run_critic(state: AgentState, llm_config) -> AgentState:

    state["answer"] = None
    state["verification"] = None

    started = perf_counter()
    state["trace"].append({"type": "agent", "agent": "critic", "status": "started"})
    stage = "prepare"
    deterministic_fields = "not_run"
    try:
        draft = state["draft"]
        if not isinstance(draft, str) or not draft.strip():
            raise ValueError("Critic requires a non-empty draft")
        if not isinstance(state["composition"], dict):
            raise ValueError("Critic requires a structured composition")

        evidence = deepcopy(build_agent_evidence(state["trace"]))
        composition = deepcopy(state["composition"])
        stage = "deterministic"

        try:
            if evidence != state["evidence"]:
                raise ValueError("Writer evidence does not match successful tool results")
            catalog = build_fact_catalog(evidence)
            Draft202012Validator(composition_schema(catalog)).validate(composition)
            template = compose_template(composition, catalog)
            expected_draft = render_agent_template(template, evidence)
            if draft != expected_draft:
                raise ValueError("Draft does not match the source-rendered composition")
        except (ValueError, ValidationError) as error:
            issue = error.message if isinstance(error, ValidationError) else str(error)
            state["verification"] = {
                "status": "failed", "supported": False, "issues": [issue],
                "stage": stage, "deterministic_fields": "failed",
                "method": "source_fields_and_llm_judge",
            }
            return state

        deterministic_fields = "passed"
        stage = "grounding_and_language"
        messages = build_agent_verification_messages(
            state["question"], draft, evidence, composition["kind"], composition["text"],
        )
        text = await asyncio.to_thread(
            request_answer_check, messages, llm_config, state["trace"], "critic", VERIFICATION_SCHEMA,
        )

        Draft202012Validator(VERIFICATION_SCHEMA).validate(json.loads(text))
        verdict = parse_agent_verdict(text)
        state["verification"] = {
            **verdict, "status": "passed" if verdict["supported"] else "failed",
            "stage": stage, "deterministic_fields": deterministic_fields,
            "method": "source_fields_and_llm_judge",
        }
        if verdict["supported"]:
            state["answer"] = draft
            
    except Exception as error:
        state["verification"] = {
            "status": "error", "supported": False,
            "issues": [f"{type(error).__name__}: {error}"],
            "stage": stage, "deterministic_fields": deterministic_fields,
            "method": "source_fields_and_llm_judge",
        }
    finally:
        if state["verification"] is None:
            state["verification"] = {
                "status": "error", "supported": False,
                "issues": ["Critic verification was interrupted"],
                "stage": stage, "deterministic_fields": deterministic_fields,
                "method": "source_fields_and_llm_judge",
            }

        verification = state["verification"]
        state["trace"].append({
            "type": "agent", "agent": "critic",
            "status": "error" if verification["status"] == "error" else "completed",
            "verification_status": verification["status"],
            "issues": deepcopy(verification["issues"]),
            "elapsed_seconds": perf_counter() - started,
        })

    return state
