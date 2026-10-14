from src.finsight.tools.agentic_tools import TOOL_FUNCTIONS


def execute_tool(name: str, arguments: dict):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Tool name must be a non-empty string")
    
    if name not in TOOL_FUNCTIONS:
        raise ValueError(f"Unknown tool: {name}")
    
    if type(arguments) is not dict:
        raise ValueError("Tool arguments must be a dictionary")

    function = TOOL_FUNCTIONS[name]
    return function(**arguments)
