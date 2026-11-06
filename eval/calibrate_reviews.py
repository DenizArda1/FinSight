"""Compare at least ten independently human-labelled cases with saved judge results."""
import argparse
from src.utils.utils import load_json, load_jsonl, save_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judged", required=True)
    parser.add_argument("--human", required=True, help="JSONL rows: id and numeric_correct/complete/language_correct labels")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    human = load_jsonl(args.human)
    if len(human) < 10 or len({row["id"] for row in human}) != len(human):
        parser.error("At least ten unique human-labelled cases are required")
    judged = {row["id"]: row.get("review") or {} for row in load_json(args.judged)}
    decisions = []
    for row in human:
        for field in ("numeric_correct", "complete", "language_correct", "refusal_correct", "injection_resisted"):
            if field in row and row[field] is not None:
                if type(row[field]) is not bool:
                    parser.error("Human labels must be booleans or null")
                actual = judged.get(row["id"], {}).get(field)
                decisions.append({"id": row["id"], "field": field, "human": row[field], "judge": actual,
                                  "agreement": actual == row[field] if actual is not None else None})
    measured = [row for row in decisions if row["agreement"] is not None]
    save_json({"human_cases": len(human), "decisions": decisions,
               "agreement": sum(row["agreement"] for row in measured) / len(measured) if measured else None}, args.output)


if __name__ == "__main__":
    main()
