import json
from copy import deepcopy

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
                        "maxLength": 400,
                    },
                    "filing_scope": {
                        "type": "string", "enum": ["annual", "recent", "any"],
                        "description": "annual for annual-report narratives; recent for quarterly reports/current events; any only when both are needed.",
                    },
                    "years": {
                        "type": "integer", "minimum": 1, "maximum": 5,
                        "description": "Minimum annual source years: 2 for year-over-year margin comparisons, 3 for comparing two growth rates.",
                    },
                    "fiscal_year": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                        "description": "The explicitly requested filing fiscal year; null for latest or unspecified periods.",
                    },
                },
                "required": ["id", "agent", "instruction", "fiscal_year", "filing_scope", "years"],
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
        if task["agent"] == "financial_data" and task["filing_scope"] == "recent":
            raise ValueError("Recent-source tasks require filing_rag, not annual financial_data")
        fiscal_year = task.get("fiscal_year")
        years = task.get("years", 1)
        if type(years) is not int or not 1 <= years <= 5:
            raise ValueError("Task years must be an integer from 1 to 5")
        if fiscal_year is not None and (type(fiscal_year) is not int or fiscal_year <= 0):
            raise ValueError("Task fiscal_year must be a positive integer or null")
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


def normalize_plan(plan):
    #Correct explicit routing contradictions and remove exact duplicate work
    # Validate structure first; do not repair unknown fields or guess from prose.
    try:
        PLANNER_VALIDATOR.validate(plan)
    except ValidationError as error:
        raise ValueError(f"Invalid planner response: {error.message}") from error
    result = deepcopy(plan)
    for task in result['tasks']:
        if task['agent'] == 'financial_data' and task['filing_scope'] == 'recent':
            task['agent'] = 'filing_rag'
    if result['tasks'] and result['request_type'] in {'financial', 'filing', 'mixed'}:
        agents = {task['agent'] for task in result['tasks']}
        result['request_type'] = ('mixed' if len(agents) == 2 else
                                  'financial' if agents == {'financial_data'} else 'filing')
    validate_plan(result)
    unique, seen = [], set()
    for task in result['tasks']:
        key = (task['agent'], ' '.join(task['instruction'].split()),
               task['filing_scope'], task['years'], task['fiscal_year'])
        if key not in seen:
            unique.append(task)
            seen.add(key)
    result['tasks'] = unique
    return result


def generate_plan(question, llm_config, telemetry=None):
    #Request a structured plan and return it only after validation
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be a non-empty string")

    messages = build_planner_messages(question.strip())

    response = generate_response(
        messages,
        llm_config,
        response_format=PLANNER_RESPONSE_SCHEMA,
        telemetry=telemetry,
    )

    try:
        plan = json.loads(response)
    except json.JSONDecodeError as error:
        raise ValueError("Planner response must be valid JSON") from error

    return normalize_plan(plan)
