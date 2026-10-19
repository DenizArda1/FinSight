import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

async def load_mcp_tool_schemas(client: Client) -> list[dict]:
    schemas = []
    cursor = None

    while True:
        listing = await client.list_tools(cursor=cursor)

        for tool in listing.tools:
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.input_schema,
                    },
                }
            )

        cursor = listing.next_cursor
        if cursor is None:
            break

    if not schemas:
        raise ValueError("MCP server did not expose any tools")

    return schemas

async def call_mcp_tool(client: Client, name: str,arguments: dict) -> dict:
    result = await client.call_tool(name, arguments)

    if result.is_error:
        error_text = "\n".join(
            item.text for item in result.content if item.type == "text"
        )
        raise RuntimeError(f"MCP tool '{name}' failed: {error_text or 'Unknown error'}")

    if not isinstance(result.structured_content, dict):
        raise ValueError(f"MCP tool '{name}' did not return a structured object")

    return result.structured_content


async def main() -> None:
    project_root = Path(__file__).resolve().parents[2]

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp.server"],
        cwd=str(project_root),
    )

    async with Client(parameters, raise_exceptions=True) as client:
        listing = await client.list_tools()

        for tool in listing.tools:
            print(f"Tool: {tool.name}")

        company = await call_mcp_tool(
            client,
            "resolve_ticker_to_cik",
            {"ticker": "AAPL"},
        )

        print("Company:", company)

        facts = await call_mcp_tool(
            client,
            "get_company_facts",
            {
                "cik": company["cik"],
                "concept": "revenue",
                "years": 1,
            },
        )

        print("Financial facts:", facts)

        search_data = await call_mcp_tool(
            client,
            "search_filings",
            {
                "ticker": "NVDA",
                "query": "export restrictions and export controls",
                "section": "Item 1A",
                "top_k": 2,
            },
        )

        for match in search_data["matches"]:
            metadata = match["metadata"]

            print("Section:", metadata["section"])
            print("Fiscal year:", metadata["fiscal_year"])
            print("Source:", metadata["source_url"])
            print("Text:", match["text"])
            print()


if __name__ == "__main__":
    asyncio.run(main())
