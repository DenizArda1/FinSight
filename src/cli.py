import argparse
import sys
from pathlib import Path
from requests import RequestException

from src.agents.single_agent import run_agent
from src.utils.utils import load_yaml
from src.verification.agent_answer import format_source_references


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
        result = run_agent(args.question, settings["llm"], verbose=args.verbose, return_details=True)
    except (RequestException, ValueError, RuntimeError, OSError) as error:
        print(f"Request failed ({type(error).__name__}): {error}", file=sys.stderr)
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
