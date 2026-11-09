from pathlib import Path
import re

from src.data.contracts import validate_calculations
from src.pipeline.run_metric_pipeline import calculate_metric_rows
from src.tools.company import resolve_company
from src.utils.utils import load_json, load_yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def validate_financial_request(cik, years):
    if not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}", cik):
        raise ValueError("CIK must be a 10-digit string")
    if type(years) is not int or not 1 <= years <= 5:
        raise ValueError("Years must be an integer between 1 and 5")


def get_company_facts(cik: str, concept: str, years: int = 5, unit: str = "USD") -> dict:
    # Read annual base metrics prepared using the configured XBRL selection rules.
    validate_financial_request(cik, years)
    config = load_yaml(PROJECT_ROOT / "configs" / "metrics.yaml")
    if not isinstance(concept, str) or concept not in config["metrics"]:
        raise ValueError(f"Unknown base metric: {concept}")

    if unit != config["metrics"][concept]["unit"]:
        raise ValueError(f"Unsupported unit for {concept}: {unit}")

    manifest = load_json(PROJECT_ROOT / "financial_data" / "raw" / cik / "manifest.json")
    if str(manifest["cik"]).zfill(10) != cik:
        raise ValueError("Company manifest CIK does not match the requested CIK")

    company = {"ticker": manifest["ticker"], "cik": cik, "name": manifest["name"]}
    period_ends = sorted({
        filing["reportDate"] for filing in manifest["filings"] if filing["form"] == "10-K"
    }, reverse=True)[:years]

    path = PROJECT_ROOT / "financial_data" / "processed" / cik / f"{concept}.json"

    if not path.is_file():
        raise FileNotFoundError(f"Prepared base metric not found for CIK {cik}: {concept}. Run the metric preparation pipeline.")
    records = load_json(path)

    if not isinstance(records, list):
        raise ValueError("Prepared metric records must be a list")

    selected = [record for record in records if record["end"] in period_ends]
    filing_urls = {
        filing["accessionNumber"]: filing["url"]
        for filing in manifest["filings"]
        if "accessionNumber" in filing and "url" in filing
    }
    seen_ends = set()
    for record in selected:
        if str(record["cik"]).zfill(10) != cik or record["metric"] != concept:
            raise ValueError("Prepared record does not match the requested company and metric")
        if record["unit"] != unit:
            raise ValueError("Prepared record unit does not match the requested unit")
        if record["end"] in seen_ends:
            raise ValueError("Multiple prepared records found for the same period end")
        seen_ends.add(record["end"])
        record["amendment_note"] = (
            "Latest filed annual value selected from 10-K/A; this can amend an earlier reported value."
            if record.get("is_amendment") or record.get("form") == "10-K/A"
            else "Latest filed annual value selected across equivalent XBRL tags; later annual comparative values take priority."
        )
        if record.get("accn") in filing_urls:
            record["source_url"] = filing_urls[record["accn"]]

    return {
        "company": company,
        "concept": concept,
        "definition": {key: config["metrics"][concept][key]
                       for key in ("description", "taxonomy", "unit", "tags")
                       if key in config["metrics"][concept]},
        "unit": unit,
        "requested_years": years,
        "available_period_count": len(period_ends),
        "history_complete": len(period_ends) == years,
        "requested_period_ends": period_ends,
        "missing_period_ends": [end for end in period_ends if end not in seen_ends],
        "records": sorted(selected, key=lambda record: record["end"], reverse=True),
    }


def compute_metrics(cik: str, metrics: list[str], years: int = 5) -> dict:
    # Load authoritative inputs locally instead of accepting model-generated numbers.
    validate_financial_request(cik, years)
    if not isinstance(metrics, list) or not metrics or any(not isinstance(name, str) for name in metrics):
        raise ValueError("Metrics must be a non-empty list of metric names")
    if len(set(metrics)) != len(metrics):
        raise ValueError("Metric names must be unique")
    config = load_yaml(PROJECT_ROOT / "configs" / "metrics.yaml")

    for name in metrics:
        if name not in config["calculations"]:
            raise ValueError(f"Unknown calculated metric: {name}")

    definitions = {name: config["calculations"][name] for name in metrics}
    validate_calculations(definitions, config["metrics"])

    facts = {}
    records = {}
    results = {}
    warnings = []
    for name, definition in definitions.items():
        for input_name in definition["inputs"]:
            if input_name not in facts:
                facts[input_name] = get_company_facts(
                    cik, input_name, years, config["metrics"][input_name]["unit"],
                )

                records[input_name] = facts[input_name]["records"]
                missing = facts[input_name]["missing_period_ends"]
                if len(facts[input_name]["requested_period_ends"]) < years:
                    warnings.append(f"Only {len(facts[input_name]['requested_period_ends'])} annual source periods available for {input_name}; requested {years}.")
                
                if missing:
                    warnings.append(f"Missing {input_name} for period ends: {', '.join(missing)}")

        if definition["period_mode"] == "same_period":
            minimum = 1
        else:
            minimum = 2
            
        if any(len(records[input_name]) < minimum for input_name in definition["inputs"]):
            results[name] = []
            warnings.append(f"Insufficient source records for {name}; at least {minimum} annual periods are required.")
            continue
        # Growth/CAGR must cover the requested window; do not silently skip missing years.
        if definition["period_mode"] != "same_period" and any(
            facts[input_name]["missing_period_ends"]
            or len(facts[input_name]["requested_period_ends"]) < years
            for input_name in definition["inputs"]
        ):
            results[name] = []
            warnings.append(f"Incomplete requested period coverage for {name}.")
            continue

        rows = calculate_metric_rows(name, definition, records)
        results[name] = sorted(rows, key=lambda row: row["end"], reverse=True)

    return {
        "company": next(iter(facts.values()))["company"],
        "requested_years": years,
        "results": results,
        "calculation_definitions": definitions,
        "warnings": warnings,
        "availability": {
            name: {"concept": name, "missing_period_ends": fact["missing_period_ends"],
                   "available_period_ends": [row["end"] for row in fact["records"]]}
            for name, fact in facts.items()
        },
    }


def get_metric(ticker, metric, limit=None):
    company = resolve_company(ticker)
    project_root = Path(__file__).resolve().parents[2]
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
    project_root = Path(__file__).resolve().parents[2]
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
        "comparison_basis": "period_end_calendar_year",
        "notes": [
            "Periods are aligned by the calendar year of their end dates, not identical fiscal calendars. "
            "Check each record's start and end dates before comparing companies."
        ],
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


def compare_companies(tickers: list[str], metrics: list[str], years: int = 3) -> dict:
    """Compare source-backed rows on common period-end years, retaining fiscal dates."""
    if not isinstance(tickers, list) or not 2 <= len(tickers) <= 5:
        raise ValueError("Compare between two and five companies")
    companies = [resolve_company(ticker) for ticker in tickers]
    if len({company["cik"] for company in companies}) != len(companies):
        raise ValueError("Companies must be unique")
    validate_financial_request(companies[0]["cik"], years)
    config = load_yaml(PROJECT_ROOT / "configs" / "metrics.yaml")
    allowed = set(config["metrics"]) | set(config["calculations"])
    if (not isinstance(metrics, list) or not metrics
            or any(not isinstance(metric, str) or metric not in allowed for metric in metrics)
            or len(set(metrics)) != len(metrics)):
        raise ValueError("Metrics must be unique names from the metric contract")
    records, comparisons, warnings = [], [], []
    for metric in metrics:
        definition = config["calculations"].get(metric)
        inputs = definition["inputs"] if definition else [metric]
        company_facts = []
        calendar_sets = []
        for company in companies:
            facts = {name: get_company_facts(company["cik"], name, 5, config["metrics"][name]["unit"])
                     for name in inputs}
            first = next(iter(facts.values()))
            ends = first.get("requested_period_ends", [row["end"] for row in first["records"]] + first.get("missing_period_ends", []))
            calendar_sets.append({int(end[:4]) for end in ends})
            company_facts.append(facts)
        source_years = sorted(set.intersection(*calendar_sets), reverse=True)[:years]
        if len(source_years) < years:
            warnings.append(f"{metric}: only {len(source_years)} common source periods available; requested {years}")
        series = []
        for company, facts in zip(companies, company_facts, strict=True):
            selected = {name: [row for row in fact["records"] if int(row["end"][:4]) in source_years]
                        for name, fact in facts.items()}
            missing = False
            for name, rows in selected.items():
                gaps = set(source_years) - {int(row["end"][:4]) for row in rows}
                if gaps:
                    missing = True
                    warnings.append(f"{company['ticker']} {name}: missing common period-end years {sorted(gaps)}")
            if definition:
                if definition["period_mode"] != "same_period" and (missing or len(source_years) < 2):
                    rows = []
                else:
                    rows = calculate_metric_rows(metric, definition, selected)
            else:
                rows = selected[metric]
            series.append(index_records_by_end_year(rows))
        common = sorted(set.intersection(*(set(index) for index in series)), reverse=True)
        metric_records = []
        for year in common:
            aligned = [index[year] for index in series]
            if len({row["unit"] for row in aligned}) != 1:
                raise ValueError(f"Incompatible units for {metric}")
            for company, row in zip(companies, aligned, strict=True):
                metric_records.append({**row, "ticker": company["ticker"], "cik": company["cik"]})
        if not metric_records:
            warnings.append(f"{metric}: no comparable records across all requested companies")
        records.extend(metric_records)
        comparisons.append({"metric": metric, "common_source_end_years": source_years,
                            "common_end_years": sorted({int(row['end'][:4]) for row in metric_records}, reverse=True)})
    return {
        "companies": companies, "requested_years": years, "records": records,
        "comparisons": comparisons, "warnings": warnings,
        "comparison_basis": "period_end_calendar_year",
        "notes": ["Fiscal calendars differ. Compare each row's fiscal year, start and end dates. "
                  "Years counts source periods; growth has one fewer interval. Missing values are never zero-filled."],
    }
