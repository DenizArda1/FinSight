from pathlib import Path
import math
import argparse
import json

from src.utils.utils import load_json, save_json


def load_results(file_path):
    path = Path(file_path)
    results = load_json(path)

    if not isinstance(results, list):
        raise ValueError("Evaluation results must be a list")
    return results

def count_statuses(results):
    counts = {
        "completed": 0,
        "withheld": 0,
        "error": 0,
        "unknown": 0,
    }
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Each evaluation result must be an object")
        
        status = result.get("status")
        if not isinstance(status, str):
            counts["unknown"] += 1
        elif status in ("completed", "withheld", "error"):
            counts[status] += 1
        else:
            counts["unknown"] += 1
    
    return counts

def summarize_durations(results):
    durations = []
    skipped_count = 0

    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Each evaluation result must be an object")
        
        duration = result.get("elapsed_seconds")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool) and math.isfinite(duration) and duration >= 0:
            durations.append(duration)
        else:
            skipped_count += 1
        
    if not durations:
        return {
            "count": 0,
            "skipped_count": skipped_count,
            "total_seconds": None,
            "average_seconds": None,
            "min_seconds": None,
            "max_seconds": None
        }
        
    return {
        "count": len(durations),
        "skipped_count": skipped_count,
        "total_seconds": sum(durations),
        "average_seconds": sum(durations) / len(durations),
        "min_seconds": min(durations),
        "max_seconds": max(durations)
    }

def count_verification_statuses(results):
    counts = {
        "passed": 0,
        "failed": 0,
        "error": 0,
        "not_run": 0,
        "unknown": 0
    }
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Each evaluation result must be an object")

        verification = result.get("verification")
        if not isinstance(verification, dict):
            counts["unknown"] += 1
            continue
        status = verification.get("status")
        if not isinstance(status, str):
            counts["unknown"] += 1
        elif status in ("passed", "failed", "error", "not_run"):
            counts[status] += 1
        else:
            counts["unknown"] += 1
    return counts


def build_summary(results):
    status_counts = count_statuses(results)
    duration_summary = summarize_durations(results)
    verification_counts = count_verification_statuses(results)

    return {
        "total_cases": len(results),
        "status_counts": status_counts,
        "durations": duration_summary,
        "verification_counts": verification_counts
    }

def main():
    parser = argparse.ArgumentParser(description="Summarize saved evaluation results")
    parser.add_argument("file_path",help="Path to a saved evaluation results JSON file")
    parser.add_argument("--output", help="Path to save the summary JSON file")
    args = parser.parse_args()
    try:
        results = load_results(args.file_path)
        summary = build_summary(results)
        if args.output:
            input_path = Path(args.file_path).resolve()
            output_path = Path(args.output).resolve()
            if input_path == output_path:
                raise ValueError("Output path must differ from input path")
            save_json(summary, output_path)
    except (OSError, ValueError) as error:
        parser.exit(status=1, message=f"Failed to summarize results: {error}\n")
    formatted_summary = json.dumps(summary, indent=2, ensure_ascii=False)
    print(formatted_summary)

if __name__ == "__main__":
    main()
