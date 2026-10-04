import json
from pathlib import Path

file_path = (
    Path(__file__).resolve().parents[1]
    / "financial_data"
    / "raw"
    / "0000320193"
    / "companyfacts.json"
    
)

with file_path.open(encoding="utf-8") as file:
    data = json.load(file)

print(data["entityName"])
print(data["cik"])
for key in data.keys():
    print(key)

print("\nTaxonomies")

for taxonomy in data["facts"].keys():
    print(taxonomy)

us_gaap = data["facts"]["us-gaap"]
revenue_tags = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]

for tag in revenue_tags:
    if tag in us_gaap:
        print(tag, "as found")
        print(us_gaap[tag]["units"].keys())
    else:
        print(tag, "has not found")

for tag in revenue_tags:
    if tag not in us_gaap:
        continue

    units = us_gaap[tag]["units"]
    if "USD" not in units or not units["USD"]:
        print(tag, "has no USD records")
        continue

    records = units["USD"]
    first_record = records[0]
    t_start = first_record["start"]
    t_end = first_record["end"]

    print("\nTag:", tag)
    print("Period:", t_start, "->", t_end)

    matching_records = []
    for record in records:
        if record["start"] == t_start and record["end"] == t_end:
            matching_records.append(record)
            print(record["val"], record["form"], record["filed"], record["accn"])
    print(len(matching_records))
