#Keep the agent's advertised tools and their Python implementations together

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
