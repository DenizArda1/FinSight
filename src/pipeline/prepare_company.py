#Prepare a requested SEC company using the existing download/metric/RAG stages
from contextlib import redirect_stdout
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


def prepare_company(identifier, *, filings=False):
    company = resolve_company(identifier)
    raw = ROOT / 'financial_data/raw' / company['cik']
    processed = ROOT / 'financial_data/processed'
    config = load_yaml(ROOT / 'configs/metrics.yaml')
    with preparation_lock(), redirect_stdout(sys.stderr):
        if not (raw / 'manifest.json').is_file():
            print(f"Preparing SEC data for {company['ticker']}...", file=sys.stderr, flush=True)
            sec_client().download_company(company['ticker'], {'cik_str': int(company['cik'])}, 5)
        if not all((processed / company['cik'] / f'{name}.json').is_file() for name in config['metrics']):
            process_company(company['cik'])
        if filings:
            prepare_company_index(company, processed)
    return company


def prepare_company_index(company, processed):

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
    if reports and expected and all(
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
        raise ValueError(f"Report preparation failed for {company['ticker']}: {failures[0]['error']}")
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
