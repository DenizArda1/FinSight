"""Build a system-by-metric table from scored runs, with explicit review coverage."""
import argparse
from collections import defaultdict
from pathlib import Path
from src.utils.utils import load_json


def ratio(numerator, denominator):
    return f"{100 * numerator / denominator:.1f}%" if denominator else "N/A"


def summary(rows):
    reviews = [row["review"] for row in rows if row.get("review") and row["review"].get("method") != "review_error"]
    numeric = [review["numeric_correct"] for review in reviews if review.get("numeric_correct") is not None]
    refusal = [review["refusal_correct"] for review in reviews if review.get("refusal_correct") is not None]
    injection = [review["injection_resisted"] for review in reviews if review.get("injection_resisted") is not None]
    legitimate = [row["review"] for row in rows if row.get("review") and "false_refusal" in row["review"]
                  and row.get("category") != "out_of_scope" and "injection" not in (row.get("category") or "")]
    return [str(len(rows)), f"{len(reviews)}/{len(rows)}", ratio(sum(numeric), len(numeric)),
            ratio(sum(r.get("citations_correct", 0) for r in reviews), sum(r.get("citations_total", 0) for r in reviews)),
            ratio(sum(r.get("claims_cited", 0) for r in reviews), sum(r.get("claims_total", 0) for r in reviews)),
            ratio(sum(r.get("claims_supported", 0) for r in reviews), sum(r.get("claims_total", 0) for r in reviews)),
            ratio(sum(refusal), len(refusal)), ratio(sum(r["false_refusal"] for r in legitimate), len(legitimate)), ratio(sum(injection), len(injection)),
            f"{sum(r['elapsed_seconds'] for r in rows)/len(rows):.2f}",
            str(sum(r.get("usage", {}).get("input_tokens", 0) + r.get("usage", {}).get("output_tokens", 0) for r in rows)),
            f"{sum(r.get('usage', {}).get('estimated_cost_usd', 0) for r in rows):.6f}"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    groups = defaultdict(list)
    signatures = set()
    for filename in args.files:
        for row in load_json(filename):
            groups[row["mode"]].append(row)
            signatures.add(row.get("dataset_sha256"))
    if len(signatures) != 1:
        parser.error("Runs must use the same dataset; do not compare different question sets")
    headers = ["System", "Cases", "Reviewed", "Numeric", "Citation precision", "Citation coverage", "Faithfulness", "Refusal", "False refusal", "Injection", "Mean seconds", "Tokens", "Estimated USD"]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for mode, rows in groups.items():
        lines.append("| " + " | ".join([mode, *summary(rows)]) + " |")
    lines.append("\nN/A means unmeasured, not success. Review scores are model judgments until human calibration. Costs exclude evaluation-judge calls and local hardware; inspect usage coverage in each run.")
    with Path(args.output).open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
