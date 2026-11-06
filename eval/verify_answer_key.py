"""Independent answer-key check against raw companyfacts, without application tools."""
import hashlib
import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAGS = {
    'revenue': ['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet'],
    'net_income': ['NetIncomeLoss'], 'cost_of_revenue': ['CostOfGoodsAndServicesSold','CostOfRevenue'],
    'operating_expenses': ['OperatingExpenses'],
}
CIKS = {'AAPL':'0000320193','MSFT':'0000789019','AMZN':'0001018724','NVDA':'0001045810'}


def raw_series(ticker, metric):
    path=ROOT/'financial_data/raw'/CIKS[ticker]/'companyfacts.json'
    facts=json.loads(path.read_text())['facts']['us-gaap']
    periods={}
    for priority,tag in enumerate(TAGS[metric]):
        for row in facts.get(tag,{}).get('units',{}).get('USD',[]):
            if row.get('form') not in ['10-K','10-K/A'] or row.get('fp')!='FY' or 'start' not in row:
                continue
            if not 350 <= (date.fromisoformat(row['end'])-date.fromisoformat(row['start'])).days <= 380:
                continue
            order=(row['filed'],-priority)
            if row['end'] not in periods or order > periods[row['end']][0]:
                periods[row['end']]=(order,row)
    return {end:item[1]['val'] for end,item in periods.items()}


def verify_expected(expected):
    checks=[]
    if isinstance(expected,list):
        for child in expected:checks.extend(verify_expected(child))
    elif isinstance(expected,dict):
        ticker=expected.get('ticker'); metric=expected.get('metric'); end=expected.get('period_end')
        if ticker and metric and 'value' in expected and end:
            if metric in TAGS:
                value=raw_series(ticker,metric)[end]
            elif metric=='net_margin':
                value=raw_series(ticker,'net_income')[end]/raw_series(ticker,'revenue')[end]
            elif metric=='revenue_growth':
                series=raw_series(ticker,'revenue');value=series[end]/series[expected['previous_period_end']]-1
            elif metric=='revenue_cagr':
                series=raw_series(ticker,'revenue');value=(series[end]/series[expected['start_period_end']])**(1/expected['periods'])-1
            else:
                raise ValueError(f'Unverified numeric metric: {metric}')
            checks.append({'ticker':ticker,'metric':metric,'expected':expected['value'],'raw_derived':value,'matches':math.isclose(value,expected['value'],rel_tol=1e-12,abs_tol=1e-12)})
        if ticker and end and isinstance(expected.get('metrics'),dict):
            for metric,value in expected['metrics'].items():
                actual=raw_series(ticker,metric)[end]
                checks.append({'ticker':ticker,'metric':metric,'expected':value,'raw_derived':actual,'matches':actual==value})
        for child in expected.values():
            if isinstance(child,(dict,list)):checks.extend(verify_expected(child))
    return checks


def main():
    cases=[json.loads(line) for line in (ROOT/'eval/golden_set.jsonl').read_text().splitlines()]
    rows=[{'id':case['id'],'checks':verify_expected(case['expected'])} for case in cases]
    result={'method':'independent raw companyfacts selection and arithmetic; no src financial tools imported',
            'raw_hashes':{ticker:hashlib.sha256((ROOT/'financial_data/raw'/cik/'companyfacts.json').read_bytes()).hexdigest() for ticker,cik in CIKS.items()},'cases':rows}
    path=ROOT/'eval/diagnostics/answer_key_audit_20261106.json'
    path.write_text(json.dumps(result,indent=2))
    checks=[check for row in rows for check in row['checks']]
    print(f'{len(checks)} numerical answer-key checks; {sum(not check["matches"] for check in checks)} mismatches')
    if any(not check['matches'] for check in checks):raise SystemExit(1)


if __name__=='__main__':main()
