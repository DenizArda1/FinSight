#Prepare a requested SEC company using the existing download/metric/RAG stages
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

from src.data.explore_facts import process_company
from src.ingestion.sec_access import preparation_lock, sec_client
from src.pipeline.run_embedding_pipeline import process_filing_embeddings
from src.pipeline.run_filing_pipeline import process_company_filings
from src.rag.index_identity import verify_collection_identity
from src.rag.vector_store import get_vector_collection, save_embedding_records
from src.tools.company import resolve_company
from src.utils.utils import load_json, load_yaml, save_json


ROOT = Path(__file__).resolve().parents[2]
REFRESH_INTERVAL = timedelta(hours=24)
# Process-local only: the next MCP session or explicit refresh can retry.
_REPORT_PREPARATION_FAILURES = {}


def refresh_due(manifest, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        checked = datetime.fromisoformat(manifest['manifest_generated_at'])
        return not timedelta(0) <= now - checked < REFRESH_INTERVAL
    except (KeyError, TypeError, ValueError):
        return True


def source_signature(raw, *, metrics=False, config=None):
    # Ignore check timestamps: unchanged downloads do not invalidate derived data.
    manifest = load_json(raw / 'manifest.json')
    digest = hashlib.sha256(json.dumps(manifest['filings'], sort_keys=True).encode())
    if metrics:
        digest.update((raw / 'companyfacts.json').read_bytes())
        digest.update(json.dumps(config, sort_keys=True).encode())
    return digest.hexdigest()


def source_matches(path, signature):
    return path.is_file() and load_json(path).get('source_signature') == signature


def prepare_company(identifier, *, filings=False, refresh=False):
    company = resolve_company(identifier)
    raw = ROOT / 'financial_data/raw' / company['cik']
    processed = ROOT / 'financial_data/processed'
    config = load_yaml(ROOT / 'configs/metrics.yaml')
    with preparation_lock(), redirect_stdout(sys.stderr):
        manifest_path = raw / 'manifest.json'
        manifest = load_json(manifest_path) if manifest_path.is_file() else {}
        if refresh or refresh_due(manifest):
            print(f"Checking SEC data for {company['ticker']}...", file=sys.stderr, flush=True)
            sec_client(refresh=True).download_company(company['ticker'], {'cik_str': int(company['cik'])}, 5)
        signature = source_signature(raw, metrics=True, config=config)
        state_path = processed / company['cik'] / 'metrics_source.json'
        metric_paths = [processed / company['cik'] / f'{name}.json' for name in config['metrics']]
        if not source_matches(state_path, signature) or not all(path.is_file() for path in metric_paths) or any(
            'fiscal_year_source' not in row for path in metric_paths for row in load_json(path)
        ):
            process_company(company['cik'])
            save_json({'source_signature': signature}, state_path)
        if filings:
            if refresh:
                _REPORT_PREPARATION_FAILURES.pop(str(raw.resolve()), None)
            prepare_company_index(company, processed)
    return company


def prepare_company_index(company, processed):

    raw = ROOT / 'financial_data/raw' / company['cik']
    signature = source_signature(raw)
    failure_key = str(raw.resolve())
    prior_failure = _REPORT_PREPARATION_FAILURES.get(failure_key)
    if prior_failure and prior_failure['signature'] == signature:
        raise ValueError(prior_failure['message'] + ' (same source already failed in this session)')
    state_path = processed / company['cik'] / 'index_source.json'
    settings = load_yaml(ROOT / 'configs/settings.yaml')
    collection = get_vector_collection(settings['vector_store'])
    summary_path = processed / 'filing_preparation_summary.json'
    summary = load_json(summary_path) if summary_path.is_file() else {'schema_version': 2, 'reports': []}
    reports = [r for r in summary['reports'] if r['cik'] == company['cik'] and r['status'] == 'prepared']
    expected = {}
    for report in reports:
        path = processed / report['chunks_path']
        if path.is_file():
            expected.update({chunk['chunk_id']: chunk for chunk in load_json(path)})
    saved = collection.get(where={'cik': company['cik']}, include=['documents', 'metadatas'])
    present = {key: (text, metadata) for key, text, metadata in
               zip(saved['ids'], saved['documents'], saved['metadatas'], strict=True)}
    revenue_path = processed / company['cik'] / 'revenue.json'
    fiscal_years = {row['end']: row['fiscal_year'] for row in load_json(revenue_path)} if revenue_path.is_file() else {}
    years_match = all(chunk['metadata'].get('fiscal_year') == fiscal_years.get(
        chunk['metadata'].get('report_date'), chunk['metadata'].get('fiscal_year')) for chunk in expected.values())
    if source_matches(state_path, signature) and years_match and reports and expected and all(
        key in present and present[key] == (chunk['text'], chunk['metadata'])
        for key, chunk in expected.items()
    ) and set(expected) == set(present):
        return
    if collection.metadata and collection.metadata.get('ready') is False:
        raise ValueError('Index synchronization is incomplete; finish the embedding pipeline before preparing another company')
    identity = verify_collection_identity(collection, settings['embedding'], initialize=True)
    reports = process_company_filings(company['ticker'])
    failures = [r for r in reports if r['status'] == 'failed']
    if failures:
        message = f"Report preparation failed for {company['ticker']}: {failures[0]['error']}"
        if all(report.get('error_type') == 'ValueError' for report in failures):
            _REPORT_PREPARATION_FAILURES[failure_key] = {'signature': signature, 'message': message}
        raise ValueError(message)
    _REPORT_PREPARATION_FAILURES.pop(failure_key, None)
    prepared = [r for r in reports if r['status'] == 'prepared']
    if not prepared:
        raise ValueError(f"No supported narrative sections for {company['ticker']}")
    config = {**settings['embedding'], 'digest': identity['embedding_digest']}
    batches = [process_filing_embeddings(report, config, collection) for report in prepared]
    # Finish downloads, parsing and embedding before publishing any index writes.
    verify_collection_identity(collection, config, initialize=True)
    collection.modify(metadata={**collection.metadata, 'ready': False})
    for records in batches:
        save_embedding_records(collection, records)
    current_ids = {record['chunk_id'] for records in batches for record in records}
    stale = set(present) - current_ids
    if stale:
        collection.delete(ids=sorted(stale))
    summary['reports'] = [r for r in summary['reports'] if r['cik'] != company['cik']] + reports
    summary['company_errors'] = [e for e in summary.get('company_errors', []) if e.get('ticker') != company['ticker']]
    summary['prepared_count'] = sum(r['status'] == 'prepared' for r in summary['reports'])
    summary['failed_count'] = sum(r['status'] == 'failed' for r in summary['reports'])
    save_json(summary, summary_path)
    collection.modify(metadata={**collection.metadata, 'ready': True})
    save_json({'source_signature': signature}, state_path)


def prepare_for_tool(name, arguments):
    # Synthetic evaluation corpora must never trigger production downloads/writes.
    if os.environ.get('FINSIGHT_PROCESSED_PATH') or os.environ.get('FINSIGHT_SETTINGS_PATH'):
        return
    if name in {'get_company_facts', 'compute_metrics'}:
        prepare_company(arguments['cik'])
    elif name in {'search_filings', 'get_filing_section'}:
        prepare_company(arguments['ticker'], filings=True)
    elif name == 'compare_companies':
        for ticker in arguments['tickers']:
            prepare_company(ticker)
