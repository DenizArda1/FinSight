from typing import Any

from mcp.server import MCPServer

from src.tools.dispatcher import execute_tool

server = MCPServer("FinSight")

@server.tool()
def resolve_ticker_to_cik(ticker: str) -> dict[str, str]:
    """Resolve a stock ticker to its company name and SEC CIK."""
    return execute_tool(
        "resolve_ticker_to_cik",
        {"ticker": ticker},
    )

@server.tool()
def get_company_facts(cik: str, concept: str, years: int = 5, unit: str = "USD") -> dict[str, Any]:
    """Retrieve annual financial facts from local SEC data.

    Resolve the ticker first. Supported concepts are revenue, net_income,
    operating_income, and gross_profit. Years must be between 1 and 5.
    """
    return execute_tool(
        "get_company_facts",
        {
            "cik": cik,
            "concept": concept,
            "years": years,
            "unit": unit,
        },
    )

@server.tool()
def compute_metrics(cik: str, metrics: list[str],years: int = 5) -> dict[str, Any]:
    """Calculate financial metrics from local source records.

    Supported metrics: gross_margin, net_margin, operating_margin,
    revenue_growth, revenue_cagr. Years must be between 1 and 5.
    Growth and CAGR require at least two periods.
    Returned margins and growth values are ratios, not percentages.
    """
    return execute_tool(
        "compute_metrics",
        {
            "cik": cik,
            "metrics": metrics,
            "years": years,
        },
    )


@server.tool()
def search_filings(ticker: str, query: str, fiscal_year: int | None = None, top_k: int = 5, section: str | None = None) -> dict[str, Any]:
    """Search locally indexed annual filings and return source excerpts.

    Optional sections: Item 1, Item 1A, Item 7.
    Use financial tools for numerical metrics.
    """
    arguments = {
        "ticker": ticker,
        "query": query,
        "top_k": top_k,
    }

    if fiscal_year is not None:
        arguments["fiscal_year"] = fiscal_year

    if section is not None:
        arguments["section"] = section

    return execute_tool("search_filings", arguments)

def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
