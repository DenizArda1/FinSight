import argparse
import sys
from pathlib import Path
from requests import RequestException
import asyncio

from src.agents.runtime import run_mcp_agent, run_mcp_orchestrator
from src.utils.utils import load_yaml
from src.verification.agent_answer import format_source_references
from src.reporting import DISCLAIMER


def format_request_error(error):
    if isinstance(error, ExceptionGroup):
        return " | ".join(format_request_error(item) for item in error.exceptions)
    notes = getattr(error, "__notes__", [])
    return " | ".join([f"{type(error).__name__}: {error}", *notes])
    
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
    parser.add_argument(
        "--mode",
        choices=["single_agent", "multi_agent"],
        default="single_agent",
        help="Choose the agent execution mode",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    try:
        settings = load_yaml(project_root / "configs" / "settings.yaml")
        if args.mode == "multi_agent":
            runner = run_mcp_orchestrator
        else:
            runner = run_mcp_agent
        result = asyncio.run(
            runner(args.question,settings["llm"],verbose=args.verbose)
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
    print("\n" + DISCLAIMER)


if __name__ == "__main__":
    main()
