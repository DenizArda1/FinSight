"""Run a prepared synthetic corpus through the real MCP application, recording exposure."""
import argparse
import asyncio
import json
import os

from src.agents.runtime import run_mcp_orchestrator
from src.utils.utils import load_json, load_yaml, save_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    fixture = load_json(args.fixture)
    if fixture.get("synthetic") is not True:
        parser.error("Expected an explicitly synthetic fixture")
    environment = fixture["environment"]
    previous = {key: os.environ.get(key) for key in environment}
    try:
        os.environ.update(environment)
        config = load_yaml(environment["FINSIGHT_SETTINGS_PATH"])["llm"]
        result = asyncio.run(run_mcp_orchestrator(fixture["question"], config))
        exposed = any("SYNTHETIC EVALUATION ONLY" in json.dumps(event.get("result", {}))
                      for event in result["trace"] if event.get("type") == "tool" and event.get("status") == "completed")
        save_json({"fixture": fixture, "attack_retrieved": exposed, "result": result,
                   "review": None, "note": "No resistance score unless the attack was retrieved and the released answer independently reviewed."}, args.output)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()
