from datetime import date
from pathlib import Path

from src.utils.utils import load_json, load_yaml, save_json
from src.data.contracts import validate_selection
from src.rag.html_parser import extract_fiscal_year
from src.tools.company import downloaded_companies


def filter_annual_records(records, selection):
    #Keep annual-duration candidates from annual filings
    annual_records = []
    allowed_forms = selection["forms"]
    min_days = selection["duration_days"]["min"]
    max_days = selection["duration_days"]["max"]
    for record in records:
        if record["form"] not in allowed_forms:
            continue
        if record.get("fp") != "FY":
            continue
        if "start" not in record or "end" not in record:
            continue
        start_date = date.fromisoformat(record["start"])
        end_date = date.fromisoformat(record["end"])
        duration_days = (end_date - start_date).days
        if min_days <= duration_days <= max_days:
            annual_records.append(record)
    return annual_records


def group_records_by_period(records):
    #Group records using their start and end dates
    records_by_period = {}
    for record in records:
        period = (record["start"], record["end"])
        if period not in records_by_period:
            records_by_period[period] = []
        records_by_period[period].append(record)
    return records_by_period


def select_latest_by_period(records_by_period):
    #Select the latest filed record within each period
    latest_by_period = {}
    for period, period_records in records_by_period.items():
        latest_record = period_records[0]
        for record in period_records:
            if record["filed"] > latest_record["filed"]:
                latest_record = record
        latest_by_period[period] = latest_record
    return latest_by_period


def merge_metric_tags(us_gaap, tags, selection, unit):
    #Prefer the newest filing across equivalent tags; use tag priority for ties.
    metric_by_period = {}
    for tag in tags:
        if tag not in us_gaap:
            continue
        units = us_gaap[tag]["units"]
        if unit not in units or not units[unit]:
            continue

        annual_records = filter_annual_records(units[unit],selection)
        records_by_period = group_records_by_period(annual_records)
        latest_by_period = select_latest_by_period(records_by_period)

        for period, latest_record in latest_by_period.items():
            if (period not in metric_by_period
                    or latest_record["filed"] > metric_by_period[period]["record"]["filed"]):
                metric_by_period[period] = {
                    "tag": tag,
                    "record": latest_record,
                }
    return metric_by_period


def build_metric_rows(cik, metric_name, metric_by_period, unit, years=5, period_ends=None):
    #Build source-preserving rows for the latest N periods
    if years < 1:
        raise ValueError("years must be positive")
    eligible_periods = [
        period for period in metric_by_period
        if period_ends is None or period[1] in period_ends
    ]
    sorted_periods = sorted(
        eligible_periods,
        key=lambda period: period[1],
        reverse=True,
    )
    metric_rows = []
    for period in sorted_periods[:years]:
        metric = metric_by_period[period]
        record = metric["record"]
        row = {
            "cik": cik,
            "metric": metric_name,
            "start": period[0],
            "end": period[1],
            "value": record["val"],
            "unit": unit,
            "tag": metric["tag"],
            "form": record["form"],
            "filed": record["filed"],
            "accn": record["accn"],
            "is_amendment": record["form"] == "10-K/A",
        }
        metric_rows.append(row)
    return metric_rows


def process_company(cik, years=5):
    # Run the configured metric pipeline for one company.
    project_root = Path(__file__).resolve().parents[2]
    file_path = project_root / "financial_data" / "raw" / cik / "companyfacts.json"
    config_path = project_root / "configs" / "metrics.yaml"

    config = load_yaml(config_path)
    validate_selection(config["selection"])
    data = load_json(file_path)
    manifest = load_json(file_path.parent / "manifest.json")
    period_ends = sorted({
        filing["reportDate"] for filing in manifest["filings"] if filing["form"] == "10-K"
    }, reverse=True)[:years]
    fiscal_years = {}
    raw_path = project_root / "financial_data" / "raw"
    for filing in manifest["filings"]:
        if filing["form"] == "10-K" and filing["reportDate"] in period_ends:
            html = (raw_path / filing["path"]).read_text(encoding="utf-8")
            fiscal_years[filing["reportDate"]] = extract_fiscal_year(html)
    results = {}

    print("Company:", data["entityName"])
    
    for metric_name, metric_config in config["metrics"].items():
        taxonomy = metric_config["taxonomy"]
        tags = metric_config["tags"]
        unit = metric_config["unit"]

        metric_by_period = merge_metric_tags(
            data["facts"].get(taxonomy, {}),
            tags,
            config["selection"],
            unit,
        )
        metric_rows = build_metric_rows(
            data["cik"], metric_name, metric_by_period, unit, years=years,
            period_ends=period_ends,
        )
        for row in metric_rows:
            row["fiscal_year"] = fiscal_years[row["end"]]
            row["period_label"] = f"FY{row['fiscal_year']} (period end: {row['end']})"
        output_path = (
            project_root / "financial_data" / "processed" / cik / f"{metric_name}.json"
        )
        save_json(metric_rows, output_path)
        results[metric_name] = metric_rows

        if len(metric_rows) < years:
            print("Warning: fewer annual periods available than requested.")

        for row in metric_rows:
            print(row["end"], row["value"], row["unit"], row["tag"], row["accn"])
        print("Saved:", output_path)

    return results


def main():
    for company in downloaded_companies():
        print("\nProcessing: ", company['ticker'])
        process_company(company['cik'], years=5)

if __name__ == "__main__":
    main()
