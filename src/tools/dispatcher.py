from jsonschema import Draft202012Validator, ValidationError

from src.tools.agentic_tools import TOOL_FUNCTIONS, TOOL_SCHEMAS


TOOL_VALIDATORS = {
    schema["function"]["name"]: Draft202012Validator(schema["function"]["parameters"])
    for schema in TOOL_SCHEMAS
}


def execute_tool(name: str, arguments: dict):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Tool name must be a non-empty string")
    
    if name not in TOOL_FUNCTIONS:
        raise ValueError(f"Unknown tool: {name}")
    
    if type(arguments) is not dict:
        raise ValueError("Tool arguments must be a dictionary")
    try:
        TOOL_VALIDATORS[name].validate(arguments)
    except ValidationError as error:
        raise ValueError(f"Invalid arguments for {name}: {error.message}") from error

    function = TOOL_FUNCTIONS[name]
    return function(**arguments)
