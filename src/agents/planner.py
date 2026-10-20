import json

from jsonschema import Draft202012Validator, ValidationError

from src.llm.client import generate_response
from src.llm.prompts import build_planner_messages

PLANNER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "request_type": {
            "type": "string",
            "enum": [
                "financial",
                "filing",
                "mixed",
                "comparison",
                "out_of_scope",
                "clarification",
            ],
        },
        "tasks": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "agent": {
                        "type": "string",
                        "enum": ["financial_data", "filing_rag"],
                    },
                    "instruction": {
                        "type": "string",
                        "minLength": 1,
                    },
                },
                "required": ["id", "agent", "instruction"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["request_type", "tasks"],
    "additionalProperties": False,
}
PLANNER_VALIDATOR = Draft202012Validator(PLANNER_RESPONSE_SCHEMA)


def validate_plan(plan):
    #Reject invalid task structures and inconsistent agent routing
    try:
        PLANNER_VALIDATOR.validate(plan)
    except ValidationError as error:
        raise ValueError(f"Invalid planner response: {error.message}") from error

    request_type = plan["request_type"]
    tasks = plan["tasks"]

    if request_type in {"out_of_scope", "clarification"}:
        if tasks:
            raise ValueError(f"{request_type} plans must not contain tasks")
    elif not tasks:
        raise ValueError(f"{request_type} plans must contain at least one task")

    seen_ids = set()
    for task in tasks:
        task_id = task["id"]
        if not task_id.strip():
            raise ValueError("Task IDs must not be blank")
        if task_id != task_id.strip():
            raise ValueError("Task IDs must not contain leading or trailing whitespace")
        if not task["instruction"].strip():
            raise ValueError("Task instructions must not be blank")
        if task_id in seen_ids:
            raise ValueError("Task IDs must be unique")
        seen_ids.add(task_id)

    agents = {task["agent"] for task in tasks}
    if request_type == "financial" and agents != {"financial_data"}:
        raise ValueError("Financial plans must use only financial_data")
    if request_type == "filing" and agents != {"filing_rag"}:
        raise ValueError("Filing plans must use only filing_rag")
    if request_type == "mixed" and agents != {"financial_data", "filing_rag"}:
        raise ValueError("Mixed plans must use both financial_data and filing_rag")


def generate_plan(question, llm_config):
    #Request a structured plan and return it only after validation
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be a non-empty string")

    messages = build_planner_messages(question.strip())

    response = generate_response(
        messages,
        llm_config,
        response_format=PLANNER_RESPONSE_SCHEMA,
    )

    try:
        plan = json.loads(response)
    except json.JSONDecodeError as error:
        raise ValueError("Planner response must be valid JSON") from error

    validate_plan(plan)
    return plan
