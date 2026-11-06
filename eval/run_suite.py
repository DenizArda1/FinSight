"""Run B0, B1 and final on one frozen dataset, then score and render their table."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from eval.run_eval import run_evaluation
from eval.naive_rag import prepare_index
from eval.snapshots import capture_snapshot
from eval.score_results import score_row
from eval.report_results import summary
from src.utils.utils import load_jsonl, load_yaml, save_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", dest="ids")
    parser.add_argument("--prepare-baseline", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    settings = load_yaml(root / "configs/settings.yaml")
    cases = load_jsonl(root / "eval/golden_set.jsonl")
    if args.ids:
        if set(args.ids) - {case["id"] for case in cases}:
            parser.error("Unknown case ID")
        cases = [case for case in cases if case["id"] in args.ids]
    if args.prepare_baseline:
        prepare_index(settings)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = root / "eval/results" / f"suite_{stamp}_{uuid4().hex[:8]}"
    directory.mkdir(parents=True)
    snapshot = capture_snapshot(root, settings)
    rubric = (root / "eval/judge_prompt.md").read_text()
    table = []
    for mode in ("baseline", "naive_rag", "multi_agent"):
        rows = run_evaluation(cases, settings["llm"], mode, directory / f"{mode}.json",
                              "mcp" if mode == "multi_agent" else "direct", snapshot)
        for row in rows:
            try:
                row["review"] = score_row(row, settings["llm"], rubric)
            except Exception as error:
                row["review"] = {"method": "review_error", "error": str(error), "human_review": None}
            save_json(rows, directory / f"{mode}_reviewed.json")
        table.append("| " + " | ".join([mode, *summary(rows)]) + " |")
    headers = "System | Cases | Reviewed | Numeric | Citation precision | Citation coverage | Faithfulness | Refusal | False refusal | Injection | Mean seconds | Tokens | Estimated USD"
    (directory / "comparison.md").write_text("| " + headers + " |\n| " + " | ".join(["---"] * 13) + " |\n" + "\n".join(table)
        + "\n\nModel-judged scores require human calibration. Missing metrics are N/A. Costs exclude judge calls, taxes and local hardware.\n")
    print(directory)


if __name__ == "__main__":
    main()
