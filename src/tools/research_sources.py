#Supplemental filing and macro tools; annual metrics remain a separate contract
import math
import re
from datetime import date
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin, urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from src.ingestion.edgar import filing_rows
from src.ingestion.public_sources import PublicSourceClient
from src.ingestion.sec_access import preparation_lock, sec_client
from src.rag.chunking import split_text
from src.rag.html_parser import extract_text
from src.tools.company import resolve_company

BLS_SERIES = {
    'cpi': ('CUUR0000SA0', 'CPI-U, all items', 'index (1982-84=100)', 'not seasonally adjusted'),
    'unemployment': ('LNS14000000', 'Unemployment rate', 'percent', 'seasonally adjusted'),
    'payrolls': ('CES0000000001', 'Total nonfarm payroll employment', 'thousand persons', 'seasonally adjusted'),
}


def validate_search(query, top_k):
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise ValueError('Query must contain 1–1000 characters')
    if type(top_k) is not int or not 1 <= top_k <= 8:
        raise ValueError('top_k must be an integer from 1 to 8')


def rank_documents(documents, query, top_k):
    """Lexical excerpt retrieval over a bounded recent corpus, with exact offsets."""
    terms = set(re.findall(r'[a-z0-9]{3,}', query.lower()))
    matches = []
    for document in documents:
        for chunk in split_text(document['text'], max_chars=3500, overlap=300):
            words = set(re.findall(r'[a-z0-9]{3,}', chunk['text'].lower()))
            score = len(terms & words)
            if score:
                matches.append({'text': chunk['text'], 'score': score,
                                'metadata': {**document['metadata'], 'start': chunk['start'], 'end': chunk['end']}})
    return sorted(matches, key=lambda item: item['score'], reverse=True)[:top_k]


def select_updates(rows, form, limit):
    selected = {row['accessionNumber']: row for row in rows if row['form'] in {form, form + '/A'}}
    return sorted(selected.values(), key=lambda row: (row['filingDate'], row['accessionNumber']), reverse=True)[:limit]


def exhibit_links(index_html, base):
    links = []
    for row in BeautifulSoup(index_html, 'html.parser').select('table.tableFile tr'):
        cells = row.find_all('td')
        if len(cells) < 4 or not cells[3].get_text(strip=True).startswith('EX-99'):
            continue
        anchor = cells[2].find('a', href=True)
        if not anchor:
            continue
        url = urljoin(base, anchor['href'])
        parsed = urlsplit(url)
        if parsed.scheme == 'https' and parsed.netloc == 'www.sec.gov' and url.startswith(base) and parsed.path.lower().endswith(('.htm', '.html')):
            links.append(url)
    return list(dict.fromkeys(links))


def search_company_updates(ticker, query, form='10-Q', limit=4, top_k=4):
    validate_search(query, top_k)
    if form not in {'10-Q', '8-K'} or type(limit) is not int or not 1 <= limit <= 8:
        raise ValueError('Choose 10-Q or 8-K and a limit from 1 to 8')
    company = resolve_company(ticker)
    documents, warnings = [], []
    with preparation_lock():
        client = PublicSourceClient(sec_client().user_agent)
        data, _ = client.json(f"https://data.sec.gov/submissions/CIK{company['cik']}.json")
        rows = select_updates(filing_rows(data['filings']['recent']), form, limit)
        for row in rows:
            accession, name = row['accessionNumber'], row['primaryDocument']
            if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession) or '/' in name or not name:
                raise ValueError('Invalid SEC document identity')
            base = f"https://www.sec.gov/Archives/edgar/data/{int(company['cik'])}/{accession.replace('-', '')}/"
            urls = [base + quote(name)]
            if form == '8-K':
                try:
                    index = client.get(base + accession + '-index.html')
                    exhibits = exhibit_links(index['text'], base)
                    urls.extend(exhibits[:3])
                    if len(exhibits) > 3:
                        warnings.append(f'{accession}: only the first three HTML EX-99 exhibits are included.')
                except Exception as error:
                    # Preserve the primary filing when its exhibit index cannot be retrieved.
                    warnings.append(f'{accession}: exhibit index unavailable ({type(error).__name__}).')
            for index, url in enumerate(urls):
                try:
                    response = client.get(url)
                    text = extract_text(response['text'])
                    if not text.strip():
                        raise ValueError('Empty cleaned filing')
                    documents.append({'text': text, 'metadata': {
                        'ticker': company['ticker'], 'form': row['form'], 'accession_number': accession,
                        'report_date': row['reportDate'], 'filed': row['filingDate'], 'source_url': url,
                        'section': 'Primary document' if index == 0 else 'EX-99 exhibit',
                        'retrieved_at': response['retrieved_at'], 'sha256': response['sha256']}})
                except Exception as error:
                    warnings.append(f'{accession}: document unavailable ({type(error).__name__}).')
    return {'company': company, 'matches': rank_documents(documents, query, top_k), 'warnings': warnings,
            'coverage': {'form': form, 'filings_considered': len(rows), 'documents_loaded': len(documents),
                         'scope': 'Recent submissions only; HTML primary documents and up to three EX-99 HTML exhibits per 8-K. PDF exhibits are not parsed.'},
            'period_warning': '10-Q may contain both quarterly and year-to-date figures. Do not treat either as annual data or infer a fourth quarter.'}


def search_fed_releases(query, top_k=4):
    validate_search(query, top_k)
    documents, warnings = [], []
    with preparation_lock():
        client = PublicSourceClient()
        feed = client.get('https://www.federalreserve.gov/feeds/press_monetary.xml')
        items = ElementTree.fromstring(feed['text']).findall('./channel/item')[:8]
        for item in items:
            url = item.findtext('link', '').strip()
            if not url.startswith('https://www.federalreserve.gov/newsevents/pressreleases/'):
                continue
            try:
                response = client.get(url)
                soup = BeautifulSoup(response['text'], 'html.parser')
                article = soup.select_one('#article') or soup.select_one('main')
                if article is None:
                    raise ValueError('Fed article body not found')
                published = parsedate_to_datetime(item.findtext('pubDate')).date().isoformat()
                documents.append({'text': extract_text(str(article)), 'metadata': {
                    'name': item.findtext('title', 'Federal Reserve'), 'publisher': 'Federal Reserve',
                    'report_date': published, 'source_url': url, 'section': 'Monetary policy release',
                    'retrieved_at': response['retrieved_at'], 'sha256': response['sha256']}})
            except Exception as error:
                warnings.append(f'{url}: unavailable ({type(error).__name__}).')
    return {'matches': rank_documents(documents, query, top_k), 'warnings': warnings,
            'coverage': 'Up to eight releases from the current monetary-policy RSS feed; not a historical archive.',
            'causality_warning': 'Macro policy statements alone do not establish a realized effect on any particular company.'}


def get_bls_series(indicator, months=12):
    if indicator not in BLS_SERIES or type(months) is not int or not 1 <= months <= 24:
        raise ValueError('Choose cpi, unemployment or payrolls and 1–24 months')
    series_id, name, unit, adjustment = BLS_SERIES[indicator]
    url = f'https://api.bls.gov/publicAPI/v1/timeseries/data/{series_id}'
    with preparation_lock():
        data, response = PublicSourceClient(ttl=86400).json(url)
    if data.get('status') != 'REQUEST_SUCCEEDED':
        raise ValueError('BLS request failed: ' + str(data.get('message', [])))
    series = data.get('Results', {}).get('series', [])
    if len(series) != 1 or series[0].get('seriesID') != series_id:
        raise ValueError('BLS series identity mismatch')
    records, missing_periods = [], []
    for row in series[0].get('data', []):
        if not re.fullmatch(r'M(0[1-9]|1[0-2])', row.get('period', '')):
            continue
        if row.get('value') in {'-', '', None}:
            missing_periods.append({'year': row['year'], 'period': row['period'], 'footnotes': row.get('footnotes', [])})
            continue
        value = float(row['value'])
        if not math.isfinite(value):
            raise ValueError('BLS returned a non-finite value')
        period = date(int(row['year']), int(row['period'][1:]), 1).isoformat()[:7]
        records.append({'metric': indicator, 'name': name, 'value': value, 'unit': unit, 'end': period,
                        'seasonal_adjustment': adjustment, 'footnotes': row.get('footnotes', []),
                        'source_url': url, 'publisher': 'BLS', 'tag': series_id,
                        'retrieved_at': response['retrieved_at']})
    records.sort(key=lambda row: row['end'], reverse=True)
    return {'records': records[:months], 'source_url': url, 'publisher': 'BLS',
            'missing_observations': missing_periods,
            'coverage': 'Latest available monthly observations from the keyless v1 API, not real-time data.',
            'warning': 'CPI is an index level, not an inflation percentage. Payrolls are employment levels, not monthly changes. Do not infer company-specific causation.'}
