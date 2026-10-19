#Run the same frozen question set and settings through direct and MCP paths.
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from eval.run_eval import run_evaluation, validate_cases
from eval.snapshots import capture_snapshot
from src.utils.utils import load_jsonl, load_yaml, save_json


def successful_payloads(row):
    return sorted({json.dumps({"tool": event["name"], "result": event["result"]}, sort_keys=True, ensure_ascii=False)
                   for event in row["trace"] if event.get("type") == "tool" and event.get("status") == "completed"})


def compare_results(direct, mcp):
    if [row["id"] for row in direct] != [row["id"] for row in mcp]:
        raise ValueError("Comparison requires matching case IDs and order")
    rows = []
    for left, right in zip(direct, mcp):
        for key in ("question", "expected", "dataset_sha256", "llm_config", "data_snapshot"):
            if left[key] != right[key]:
                raise ValueError(f"Comparison input mismatch: {key}")
        rows.append({
            "id": left["id"],
            "direct_status": left["status"], "mcp_status": right["status"],
            "same_status": left["status"] == right["status"],
            "same_verification_status": left["verification"]["status"] == right["verification"]["status"],
            "same_successful_tool_payloads": successful_payloads(left) == successful_payloads(right),
            "exact_answer_match": (left["answer"] == right["answer"]
                                   if left["answer"] is not None and right["answer"] is not None else None),
            "direct_elapsed_seconds": left["elapsed_seconds"], "mcp_elapsed_seconds": right["elapsed_seconds"],
            "manual_review": None,
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", dest="case_ids")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    settings = load_yaml(root / "configs" / "settings.yaml")
    cases = load_jsonl(root / "eval" / "golden_set.jsonl")
    validate_cases(cases)

    if args.case_ids:
        if set(args.case_ids) - {case["id"] for case in cases}:
            parser.error("Unknown case ID")
        cases = [case for case in cases if case["id"] in args.case_ids]
    # A fixed seed reduces sampling differences; both paths receive the same config.
    
    config = deepcopy(settings["llm"])
    config.setdefault("options", {}).setdefault("seed", 0)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + "_" + uuid4().hex[:8]
    directory = root / "eval" / "results"
    snapshot = capture_snapshot(root, settings)
    paths = {transport: directory / f"comparison_{run_id}_{transport}.json" for transport in ("direct", "mcp")}
    report_path = directory / f"comparison_{run_id}.json"
    print(f"Comparison: {report_path}", flush=True)

    results = {}
    for transport in ("direct", "mcp"):
        print(f"Transport: {transport}", flush=True)
        results[transport] = run_evaluation(cases, config, transport=transport,
                                           output_path=paths[transport], data_snapshot=snapshot)
    final_snapshot = capture_snapshot(root, settings)
    report = {
        "schema_version": 1, "direct_path": str(paths["direct"]), "mcp_path": str(paths["mcp"]),
        "initial_snapshot": snapshot, "final_snapshot": final_snapshot,
        "inputs_unchanged": snapshot == final_snapshot,
        "llm_config": config,
        "note": "Exact text and tool equality are diagnostics, not semantic correctness scores. Review answers against the expected facts.",
        "cases": compare_results(results["direct"], results["mcp"]),
    }

    save_json(report, report_path)
    print(f"Saved comparison: {report_path}", flush=True)
    if not report["inputs_unchanged"]:
        raise RuntimeError("Data or code changed during the comparison; results are not a controlled pair")


if __name__ == "__main__":
    main()
