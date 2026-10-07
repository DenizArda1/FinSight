from datetime import date
from pathlib import Path

from src.finsight.metrics.calculations import (
    calculate_cagr,
    calculate_growth,
    calculate_margin,
    index_rows_by_period,
)
from src.finsight.data.contracts import validate_calculations
from src.finsight.utils.utils import load_json, load_yaml, save_json


def match_income_records(revenue_rows, income_rows):
    #Return period-matched record pairs and identify missing periods
    revenue_by_period = index_rows_by_period(revenue_rows)
    income_by_period = index_rows_by_period(income_rows)
    matches = []

    for period, revenue_record in revenue_by_period.items():
        if period not in income_by_period:
            print("Missing income period:", period)
            continue

        income_record = income_by_period[period]
        matches.append((period, revenue_record, income_record))

    for period in income_by_period:
        if period not in revenue_by_period:
            print("Missing revenue period:", period)

    return matches

def build_margin_rows(matches, margin_type, income_type, revenue_type="revenue"):
    margin_rows = []
    for period, revenue_record, income_record in matches:
        if revenue_record["cik"] != income_record["cik"]:
            raise ValueError("Company mismatch")

        if revenue_record["unit"] != income_record["unit"]:
            raise ValueError("Unit mismatch")

        margin = calculate_margin(income_record["value"],revenue_record["value"])
        margin_rows.append({
            "cik": revenue_record["cik"],
            "start": period[0],
            "end": period[1],
            "value": margin,
            "unit": "ratio",
            "metric": margin_type,
            "formula": f"{income_type} / {revenue_type}",
            "inputs": {
                income_type: income_record,
                revenue_type: revenue_record,
            },
        })
    return margin_rows

def build_growth_rows(pairs, metric_name="revenue_growth", input_type="revenue"):
    growth_rows = []
    for previous_record, current_record in pairs:
        growth = calculate_growth(previous_record["value"],current_record["value"])
        growth_rows.append({
            "cik": current_record["cik"],
            "metric": metric_name,
            "start": current_record["start"],
            "end": current_record["end"],
            "value": growth,
            "unit": "ratio",
            "formula": f"current_{input_type} / previous_{input_type} - 1",
            "inputs": {
                f"previous_{input_type}": previous_record,
                f"current_{input_type}": current_record,
            },
        })
    return growth_rows

def build_cagr_row(revenue_rows, metric_name="revenue_cagr", input_type="revenue"):
    if len(revenue_rows) < 2:
        raise ValueError("At least two revenue records are required")
    
    pairs = pair_consecutive_periods(revenue_rows)
    first_record = pairs[0][0]
    last_record = pairs[-1][1]
    periods = len(pairs)

    cagr = calculate_cagr(first_record["value"],last_record["value"],periods)

    return ({
        "cik": first_record["cik"],
        "metric": metric_name,
        "start": first_record["end"],
        "end": last_record["end"],
        "periods": periods,
        "value": cagr,
        "unit": "ratio",
        "formula": f"(end_{input_type} / start_{input_type}) ** (1 / periods) - 1",
        "inputs": {
            f"start_{input_type}": first_record,
            f"end_{input_type}": last_record,
        },
    })
    
def pair_consecutive_periods(rows):
    index_rows_by_period(rows)
    sorted_rows = sorted(rows, key=lambda row: row["end"])

    pairs = []
    for i in range(1, len(sorted_rows)):
        previous_record = sorted_rows[i-1]
        current_record = sorted_rows[i]
        if previous_record["cik"] != current_record["cik"]:
            raise ValueError("Company mismatch")

        if previous_record["unit"] != current_record["unit"]:
            raise ValueError("Unit mismatch")

        previous_end = date.fromisoformat(previous_record["end"])
        current_start = date.fromisoformat(current_record["start"])

        gap_days = (current_start - previous_end).days
        if gap_days != 1:
            raise ValueError("Annual periods are not consecutive")
        pairs.append((previous_record, current_record))
    return pairs

def process_company_calculations(cik, calculations, metrics):
    validate_calculations(calculations, metrics)
    project_root = Path(__file__).resolve().parents[3]
    company_path = project_root / "financial_data" / "processed" / cik
    records = {}
    results = {}

    for calculation_name, definition in calculations.items():
        input_names = definition["inputs"]
        for metric_name in input_names:
            if metric_name not in records:
                records[metric_name] = load_json(company_path / f"{metric_name}.json")

        function_name = definition["function"]
        if function_name == "calculate_margin":
            income_type, revenue_type = input_names
            matches = match_income_records(records[revenue_type], records[income_type])
            rows = build_margin_rows(
                matches, calculation_name, income_type, revenue_type
            )
        elif function_name == "calculate_growth":
            input_type = input_names[0]
            pairs = pair_consecutive_periods(records[input_type])
            rows = build_growth_rows(pairs, calculation_name, input_type)
        elif function_name == "calculate_cagr":
            input_type = input_names[0]
            rows = [build_cagr_row(records[input_type], calculation_name, input_type)]
        else:
            raise ValueError(f"Unsupported function for {calculation_name}")

        save_json(rows, company_path / f"{calculation_name}.json")
        results[calculation_name] = rows
        print(f"{calculation_name}: {len(rows)} records")

    return results


def main():

    project_root = Path(__file__).resolve().parents[3]
    config = load_yaml(project_root / "configs" / "metrics.yaml")

    companies = {
        "NVDA": "0001045810",
        "AAPL": "0000320193",
        "MSFT": "0000789019",
        "AMZN": "0001018724",
    }

    for ticker, cik in companies.items():
        print("\nProcessing:", ticker)
        process_company_calculations(cik, config["calculations"], config["metrics"])

if __name__ == "__main__":
    main()
