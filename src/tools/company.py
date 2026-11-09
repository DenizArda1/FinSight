from pathlib import Path
import re

from src.ingestion.sec_access import preparation_lock, sec_client
from src.utils.utils import load_json

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def downloaded_companies():
    companies = []
    for path in sorted((PROJECT_ROOT / 'financial_data/raw').glob('*/manifest.json')):
        if not re.fullmatch(r'[0-9]{10}', path.parent.name):
            continue
        manifest = load_json(path)
        if str(manifest['cik']).zfill(10) != path.parent.name:
            raise ValueError('Manifest company identity does not match its directory')
        companies.append({'ticker': manifest['ticker'], 'cik': path.parent.name, 'name': manifest['name']})
    return companies


def normalized_name(value):
    words = re.sub(r'[^a-z0-9]+', ' ', value.casefold()).split()
    while words and words[-1] in {'inc', 'incorporated', 'corp', 'corporation', 'co', 'company', 'ltd', 'limited', 'plc'}:
        words.pop()
    return ' '.join(words)


def directory_match(identifier, companies):
    exact = [c for c in companies.values() if c['ticker'].casefold() == identifier.casefold()]
    if not exact and identifier.isascii() and identifier.isdigit():
        exact = [c for c in companies.values() if int(c['cik_str']) == int(identifier)]
    if not exact:
        name = normalized_name(identifier)
        exact = [c for c in companies.values() if name and normalized_name(c['title']) == name]
    by_cik = {str(c['cik_str']).zfill(10): c for c in exact}
    if len(by_cik) > 1:
        raise ValueError('Ambiguous company name; provide its ticker or SEC CIK')
    if exact:
        company = exact[0]
        return {'ticker': company['ticker'], 'name': company['title'], 'cik': str(company['cik_str']).zfill(10)}
    return None


def resolve_company(ticker: str) -> dict[str, str]:
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError('Company identifier must be a non-empty ticker, company name or CIK')
    identifier = ticker.strip()
    path = PROJECT_ROOT / 'financial_data/raw/company_tickers.json'
    companies = load_json(path) if path.is_file() else {}
    result = directory_match(identifier, companies)
    if result:
        return result
    with preparation_lock():
        if identifier.isascii() and identifier.isdigit():
            if not 1 <= len(identifier) <= 10 or int(identifier) == 0:
                raise ValueError('CIK must contain 1 to 10 digits and be positive')
            cik = identifier.zfill(10)
            data = sec_client().fetch(f'https://data.sec.gov/submissions/CIK{cik}.json',
                                     path.parent / cik / 'submissions.json', json_data=True)
            if int(data['cik']) != int(cik):
                raise ValueError('SEC identity does not match the requested CIK')
            return {'ticker': next(iter(data.get('tickers', [])), cik), 'name': data['name'], 'cik': cik}
        companies = sec_client(refresh=True).fetch('https://www.sec.gov/files/company_tickers.json', path, json_data=True)
    result = directory_match(identifier, companies)
    if result is None:
        raise ValueError('Company not found in the SEC ticker directory; provide an exact ticker, company name or CIK')
    return result
