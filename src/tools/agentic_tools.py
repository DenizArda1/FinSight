#Keep the agent's advertised tools and their Python implementations together

from copy import deepcopy

from src.tools.company import resolve_company
from src.tools.financial_metrics import get_company_facts, compute_metrics
from src.tools.report_search import get_filing_section, search_company_reports
from src.tools.schemas import (
    RESOLVE_TICKER_TOOL, SEARCH_FILINGS_TOOL, GET_COMPANY_FACTS_TOOL, COMPUTE_METRICS_TOOL,
    GET_FILING_SECTION_TOOL,
)


TOOL_SCHEMAS = [RESOLVE_TICKER_TOOL, GET_COMPANY_FACTS_TOOL, COMPUTE_METRICS_TOOL, SEARCH_FILINGS_TOOL, GET_FILING_SECTION_TOOL]

TOOL_FUNCTIONS = {
    "resolve_ticker_to_cik": resolve_company,
    "search_filings": search_company_reports,
    "get_company_facts": get_company_facts,
    "compute_metrics": compute_metrics,
    "get_filing_section": get_filing_section,
}

AGENT_TOOL_NAMES = {
    "financial_data": {
        "resolve_ticker_to_cik",
        "get_company_facts",
        "compute_metrics",
    },
    "filing_rag": {
        "resolve_ticker_to_cik",
        "search_filings",
        "get_filing_section",
    },
}


def get_agent_tool_schemas(agent_name, tool_schemas):
    if not isinstance(agent_name, str) or agent_name not in AGENT_TOOL_NAMES:
        raise ValueError(f"Unknown agent: {agent_name}")
    if not isinstance(tool_schemas, list):
        raise ValueError("Tool schemas must be a list")

    allowed_names = AGENT_TOOL_NAMES[agent_name]
    selected_schemas = []
    selected_names = set()

    for schema in tool_schemas:
        if not isinstance(schema, dict) or not isinstance(schema.get("function"), dict):
            raise ValueError("Each tool schema must contain a function object")
        tool_name = schema["function"].get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("Tool names must be non-empty strings")

        if tool_name in allowed_names:
            if tool_name in selected_names:
                raise ValueError(f"Duplicate tool schema: {tool_name}")
            selected_schemas.append(deepcopy(schema))
            selected_names.add(tool_name)

    missing_names = allowed_names - selected_names
    if missing_names:
        raise ValueError(f"Missing tools for {agent_name}: {', '.join(sorted(missing_names))}")

    return selected_schemas
