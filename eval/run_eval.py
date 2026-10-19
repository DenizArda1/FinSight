from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import argparse
import asyncio
import hashlib
import json
from copy import deepcopy
from time import perf_counter

from src.utils.utils import load_jsonl, load_yaml, save_json
from src.agents.single_agent import run_agent
from src.agents.runtime import run_mcp_agent
from src.llm.client import generate_response

def validate_cases(cases):
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation cases must be a non-empty list")
    ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Each evaluation case must be an object")
        for field in ("id", "question", "answer_language"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError(f"Evaluation {field} must be non-empty text")
        if case["id"] in ids:
            raise ValueError(f"Duplicate evaluation ID: {case['id']}")
        if not isinstance(case.get("expected"), dict):
            raise ValueError("Evaluation expected must be an object")
        ids.add(case["id"])


def run_evaluation(cases, llm_config, mode="single_agent", output_path=None, transport="direct", data_snapshot=None):
    if transport not in ("direct", "mcp"):
        raise ValueError(f"Unknown tool transport: {transport}")
    if mode == "baseline" and transport != "direct":
        raise ValueError("Baseline has no tools; MCP transport does not apply")
    if mode == "single_agent":
        runner = run_agent
    elif mode == "baseline":
        runner = run_baseline
    else:
        raise ValueError(f"Unknown evaluation mode: {mode}")
    validate_cases(cases)
    if output_path is not None and Path(output_path).exists():
        raise FileExistsError(f"Evaluation output already exists: {output_path}")
    dataset_hash = hashlib.sha256(json.dumps(cases, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    results = []

    for case in cases:
        answer = None
        error = None
        trace = []
        details = {}
        verification = {"status": "not_run", "supported": None, "issues": []}
        started = perf_counter()

        try:
            if mode == "single_agent":
                if transport == "mcp":
                    details = asyncio.run(run_mcp_agent(case["question"], llm_config, trace=trace))
                else:
                    details = runner(case["question"], llm_config, return_details=True, trace=trace)
                answer = details["answer"]
                verification = details["verification"]
                status = details["status"]
            else:
                answer = runner(case["question"], llm_config)
                status = "completed"
        except Exception as exc:
            status = "error"
            error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }

        results.append({
            "id": case["id"],
            "question": case["question"],
            "expected": case["expected"],
            "answer_language": case["answer_language"],
            "answer": answer,
            "review": None,
            "status": status,
            "error": error,
            "mode": mode,
            "transport": transport if mode == "single_agent" else "none",
            "data_snapshot": deepcopy(data_snapshot),
            "verification": verification,
            "draft": details.get("draft"),
            "candidate": details.get("candidate"),
            "template": details.get("template"),
            "composition": details.get("composition"),
            "evidence": details.get("evidence", []),
            "trace": deepcopy(trace),
            "elapsed_seconds": perf_counter() - started,
            "model": llm_config.get("model"),
            "llm_config": {key: deepcopy(llm_config[key]) for key in ("model", "base_url", "timeout_seconds", "options") if key in llm_config},
            "dataset_sha256": dataset_hash,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
        if output_path is not None:
            save_json(results, output_path)
        print(f"{case['id']}: {status}", flush=True)

    return results

def run_baseline(question, llm_config):
    messages = [
        {
            "role": "system",
            "content": (
                "You are a financial research assistant. "
                "Never invent missing data or source references. "
                "Do not provide investment recommendations, "
                "price targets, or return forecasts. "
                "Answer in the same language as the user's question."
            ),
        },
        {"role": "user", "content": question},
    ]

    return generate_response(messages, llm_config)

def main():
    parser = argparse.ArgumentParser(description="Run FinSight evaluation cases.")
    parser.add_argument(
        "--mode",
        choices=["single_agent", "baseline"],
        default="single_agent",
    )
    parser.add_argument("--case", action="append", dest="case_ids", help="Run a specific case ID; repeat to select more cases.")
    parser.add_argument("--transport", choices=["direct", "mcp"], default="direct",
                        help="Tool execution path; use mcp to evaluate the application's CLI path.")
    args = parser.parse_args()
    if args.mode == "baseline" and args.transport != "direct":
        parser.error("Baseline has no tools; --transport mcp does not apply")
    project_root = Path(__file__).resolve().parents[1]

    cases = load_jsonl(project_root / "eval" / "golden_set.jsonl")
    validate_cases(cases)
    if args.case_ids:
        unknown = set(args.case_ids) - {case["id"] for case in cases}
        if unknown:
            parser.error(f"Unknown case IDs: {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case["id"] in args.case_ids]
    settings = load_yaml(project_root / "configs" / "settings.yaml")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    run_id = f"{timestamp}_{uuid4().hex[:8]}"
    label = f"{args.mode}_{args.transport}" if args.mode == "single_agent" else args.mode
    output_path = project_root / "eval" / "results" / f"{label}_{run_id}.json"
    print(f"Results: {output_path}", flush=True)
    from eval.snapshots import capture_snapshot
    snapshot = capture_snapshot(project_root, settings)
    results = run_evaluation(cases, settings["llm"], mode=args.mode, output_path=output_path,
                             transport=args.transport, data_snapshot=snapshot)
    print(f"Saved {len(results)} results to {output_path}")


if __name__ == "__main__":
    main()
