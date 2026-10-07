from pathlib import Path

from src.finsight.metrics.calculations import index_rows_by_period, calculate_margin, calculate_growth, calculate_cagr
from src.finsight.utils.utils import load_json, save_json
from datetime import date

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

def build_margin_rows(matches, margin_type, income_type):
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
            "formula": f"{income_type} / revenue",
            "inputs": {
                income_type: income_record,
                "revenue": revenue_record,
            },
        })
    return margin_rows

def build_growth_rows(pairs):
    growth_rows = []
    for previous_record, current_record in pairs:
        growth = calculate_growth(previous_record["value"],current_record["value"])
        growth_rows.append({
            "cik": current_record["cik"],
            "metric": "revenue_growth",
            "start": current_record["start"],
            "end": current_record["end"],
            "value": growth,
            "unit": "ratio",
            "formula": "current_revenue / previous_revenue - 1",
            "inputs": {
                "previous_revenue": previous_record,
                "current_revenue": current_record,
            },
        })
    return growth_rows

def build_cagr_row(revenue_rows):
    if len(revenue_rows) < 2:
        raise ValueError("At least two revenue records are required")
    
    pair_consecutive_periods(revenue_rows)
    sorted_rows = sorted(revenue_rows, key= lambda row: row["end"])
    first_record = sorted_rows[0]
    last_record = sorted_rows[-1]
    periods = len(sorted_rows) - 1

    cagr = calculate_cagr(first_record,last_record,periods)

    return ({
        "cik": first_record["cik"],
        "metric": "revenue_cagr",
        "start": first_record["end"],
        "end": last_record["end"],
        "periods": periods,
        "value": cagr,
        "unit": "ratio",
        "formula": "(end_revenue / start_revenue) ** (1 / periods) - 1",
        "inputs": {
            "start_revenue": first_record,
            "end_revenue": last_record,
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

def process_company_margins(cik):
    project_root = Path(__file__).resolve().parents[1]
    company_path = project_root / "financial_data" / "processed" / cik
    revenue_rows = load_json(company_path / "revenue.json")
    net_income_rows = load_json(company_path / "net_income.json")
    operating_income_rows = load_json(company_path / "operating_income.json")
    pairs = pair_consecutive_periods(revenue_rows)
    matches = match_income_records(revenue_rows, net_income_rows)

    for previous_record, current_record in pairs:
        print(previous_record["end"], "->", current_record["end"])

    operating_matches = match_income_records(
        revenue_rows,
        operating_income_rows,
    )

    print("Matched operating income periods:", len(operating_matches))

    net_margin_rows = build_margin_rows(
        matches, "net_margin", "net_income"
    )

    operating_margin_rows = build_margin_rows(
        operating_matches, "operating_margin", "operating_income"
    )
    growth_rows = build_growth_rows(pairs)

    cagr_row = build_cagr_row(revenue_rows)

    save_json([cagr_row],company_path / "revenue_cagr.json")
    save_json(growth_rows, company_path / "revenue_growth.json")
    save_json(net_margin_rows, company_path / "net_margin.json")
    save_json(operating_margin_rows, company_path / "operating_margin.json")

    return {
        "net_margin": net_margin_rows,
        "operating_margin": operating_margin_rows,
        "revenue_growth": growth_rows,
        "revenue_cagr": [cagr_row]
    }

def main():
    companies = {
        "NVDA": "0001045810",
        "AAPL": "0000320193",
        "MSFT": "0000789019",
        "AMZN": "0001018724",
    }

    for ticker, cik in companies.items():
        print("\nProcessing:", ticker)
        process_company_margins(cik)

if __name__ == "__main__":
    main()
