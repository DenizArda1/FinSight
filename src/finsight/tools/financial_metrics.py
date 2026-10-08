from pathlib import Path

from src.finsight.tools.company import resolve_company
from src.finsight.utils.utils import load_json, load_yaml


def get_metric(ticker, metric, limit=None):
    company = resolve_company(ticker)
    project_root = Path(__file__).resolve().parents[3]
    config = load_yaml(project_root / "configs" / "metrics.yaml")

    if not isinstance(metric, str) or not metric.strip():
        raise ValueError("Metric must be a non-empty string")

    metric = metric.strip()
    if metric not in config["metrics"] and metric not in config["calculations"]:
        raise ValueError(f"Unknown metric: {metric}")

    file_path = (
        project_root / "financial_data" / "processed" / company["cik"]
        / f"{metric}.json"
    )
    if not file_path.is_file():
        raise FileNotFoundError(f"Processed metric data not found for {company['ticker']}: {metric}")

    records = load_json(file_path)
    if limit is not None:
        if type(limit) is not int or limit <= 0:
            raise ValueError("Limit should be a positive integer")
    records = sorted(records, key= lambda record: record["end"], reverse=True)
    if limit is not None:
        records = records[:limit]

    return {
        "company": company,
        "metric": metric,
        "records": records,
    }

def compare_metric(tickers, metric, limit=None):
    if type(tickers) is not list or len(tickers) < 2:
        raise ValueError("At least two tickers are required")

    if limit is not None:
        if type(limit) is not int or limit <= 0:
            raise ValueError("Limit must be a positive integer")

    results = []
    for ticker in tickers:
        results.append(get_metric(ticker, metric))

    metric = results[0]["metric"]
    project_root = Path(__file__).resolve().parents[3]
    config = load_yaml(project_root / "configs" / "metrics.yaml")
    calculation = config["calculations"].get(metric, {})
    if calculation.get("period_mode") == "full_range":
        raise ValueError("Full-range metrics require a separate interval comparison")

    indexes = []
    for result in results:
        company_index = index_records_by_end_year(result["records"])
        indexes.append(company_index)

    common_years = set(indexes[0].keys())
    for company_index in indexes[1:]:
        common_years = common_years.intersection(company_index.keys())

    common_years = sorted(common_years, reverse=True)
    if not common_years:
        raise ValueError("No common period end years found")

    if limit is not None:
        common_years = common_years[:limit]

    for position, result in enumerate(results):
        company_index = indexes[position]
        selected_records = []
        for year in common_years:
            selected_records.append(company_index[year])
        result["records"] = selected_records

    return {
        "metric": metric,
        "common_years": common_years,
        "results": results,
    }

def index_records_by_end_year(records):
    records_by_year = {}
    for record in records:
        year = int(record["end"][:4])
        if year in records_by_year:
            raise ValueError("Year is already in dictionary")
        records_by_year[year] = record
    return records_by_year
