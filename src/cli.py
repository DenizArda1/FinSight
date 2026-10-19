import argparse
import sys
from pathlib import Path
from requests import RequestException
import asyncio

from mcp import Client, StdioServerParameters

from src.agents.single_agent import run_agent_async
from src.utils.utils import load_yaml
from src.verification.agent_answer import format_source_references
from src.mcp.client import load_mcp_tool_schemas


def format_request_error(error):
    if isinstance(error, ExceptionGroup):
        return " | ".join(format_request_error(item) for item in error.exceptions)
    return f"{type(error).__name__}: {error}"


async def run_mcp_agent(question, llm_config, verbose=False):
    project_root = Path(__file__).resolve().parents[1]

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp.server"],
        cwd=str(project_root),
    )

    async with Client(parameters, raise_exceptions=True) as client:
        tool_schemas = await load_mcp_tool_schemas(client)

        return await run_agent_async(
            question,
            llm_config,
            verbose=verbose,
            return_details=True,
            mcp_client=client,
            tool_schemas=tool_schemas,
        )

def main():
    parser = argparse.ArgumentParser(
        description="Ask FinSight a financial research question."
    )
    parser.add_argument("question", help="Question to send to the agent")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show tool calls and results",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    try:
        settings = load_yaml(project_root / "configs" / "settings.yaml")
        result = asyncio.run(
            run_mcp_agent(args.question,settings["llm"],verbose=args.verbose)
        )
    except (RequestException, ValueError, RuntimeError, OSError, ExceptionGroup) as error:
        print(f"Request failed ({format_request_error(error)})", file=sys.stderr)
        raise SystemExit(1) from None
    if result["answer"] is None:
        print(f"Answer withheld: verification {result['verification']['status']}.", file=sys.stderr)
        if args.verbose:
            for issue in result["verification"]["issues"]:
                print(f"- {issue}", file=sys.stderr)
        raise SystemExit(1)
    print(result["answer"])
    sources = format_source_references(result["answer"], result["evidence"])
    if sources:
        print("\n" + sources)


if __name__ == "__main__":
    main()
