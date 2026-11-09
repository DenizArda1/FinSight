import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.ingestion.edgar import EdgarClient
from src.pipeline.prepare_company import prepare_company, prepare_company_index, preparation_lock
from src.tools.company import directory_match
from src.tools.dispatcher import execute_tool
from src.utils.utils import load_json, save_json, save_yaml


class CompanyDirectoryTests(unittest.TestCase):
    def test_ticker_name_and_cik_are_not_limited_to_demo_companies(self):
        companies = {'0': {'ticker': 'ADBE', 'title': 'ADOBE INC.', 'cik_str': 796343}}
        for identifier in ('adbe', 'Adobe', 'Adobe Inc.', '796343', '0000796343'):
            with self.subTest(identifier=identifier):
                result = directory_match(identifier, companies)
                self.assertEqual(result['ticker'], 'ADBE')
                self.assertEqual(result['cik'], '0000796343')
        self.assertIsNone(directory_match('Unknown', companies))

    def test_ambiguous_names_are_not_guessed(self):
        companies = {'0': {'ticker': 'ONE', 'title': 'Example Inc.', 'cik_str': 1},
                     '1': {'ticker': 'TWO', 'title': 'Example Corp.', 'cik_str': 2}}
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            directory_match('Example', companies)


class AnnualHistoryTests(unittest.TestCase):
    def test_short_history_is_downloaded_without_inventing_periods(self):
        with TemporaryDirectory() as directory:
            client = EdgarClient('FinSight test@unit.invalid', directory)
            submissions = {'cik': 42, 'name': 'Young Company', 'filings': {'recent': {
                'accessionNumber': ['0000000042-26-000001'], 'form': ['10-K'],
                'filingDate': ['2026-02-01'], 'reportDate': ['2025-12-31'],
                'primaryDocument': ['annual.htm']}}}
            with patch.object(client, 'fetch', side_effect=[submissions, {'cik': 42}, b'<html>report</html>']):
                result = client.download_company('YOUNG', {'cik_str': 42}, 5)
            self.assertEqual(result['requested_periods'], 5)
            self.assertEqual(result['available_periods'], 1)
            self.assertEqual(len(result['filings']), 1)

    def test_other_annual_forms_are_not_mislabelled_as_ten_k(self):
        with TemporaryDirectory() as directory:
            client = EdgarClient('FinSight test@unit.invalid', directory)
            submissions = {'cik': 42, 'name': 'Foreign Company', 'filings': {'recent': {
                'accessionNumber': ['0000000042-26-000001'], 'form': ['20-F'],
                'filingDate': ['2026-02-01'], 'reportDate': ['2025-12-31'],
                'primaryDocument': ['annual.htm']}}}
            with patch.object(client, 'fetch', side_effect=[submissions, {'cik': 42}]):
                with self.assertRaisesRegex(ValueError, 'No supported 10-K.*20-F'):
                    client.download_company('FOREIGN', {'cik_str': 42}, 5)


class PreparationTests(unittest.TestCase):
    def test_cached_metrics_do_not_download_or_embed(self):
        company = {'ticker': 'ADBE', 'cik': '0000796343', 'name': 'Adobe'}
        with TemporaryDirectory() as directory, patch('src.pipeline.prepare_company.ROOT', Path(directory)), \
             patch('src.ingestion.sec_access.ROOT', Path(directory)), \
             patch('src.pipeline.prepare_company.resolve_company', return_value=company), \
             patch('src.pipeline.prepare_company.sec_client') as client, \
             patch('src.pipeline.prepare_company.process_company') as metrics, \
             patch('src.pipeline.prepare_company.prepare_company_index') as index:
            root = Path(directory)
            save_yaml({'metrics': {'revenue': {}}}, root / 'configs/metrics.yaml')
            save_json({}, root / 'financial_data/raw/0000796343/manifest.json')
            save_json([], root / 'financial_data/processed/0000796343/revenue.json')
            self.assertEqual(prepare_company('ADBE'), company)
            client.assert_not_called()
            metrics.assert_not_called()
            index.assert_not_called()
            prepare_company('ADBE', filings=True)
            index.assert_called_once()
            # Resolution of a non-listed CIK can enter the lock while preparation holds it.
            with preparation_lock(), preparation_lock():
                pass

    def test_invalid_tool_arguments_never_trigger_preparation(self):
        with patch('src.tools.dispatcher.prepare_for_tool') as prepare:
            with self.assertRaises(ValueError):
                execute_tool('get_company_facts', {'cik': '0000796343', 'concept': 'revenue', 'years': True}, prepare=True)
            prepare.assert_not_called()

    def test_preparation_precedes_tool_execution_only_when_requested(self):
        with patch('src.tools.dispatcher.prepare_for_tool') as prepare, \
             patch.dict('src.tools.dispatcher.TOOL_FUNCTIONS', {'get_company_facts': lambda **args: {'ok': True}}):
            args = {'cik': '0000796343', 'concept': 'revenue', 'years': 1}
            self.assertEqual(execute_tool('get_company_facts', args, prepare=True), {'ok': True})
            prepare.assert_called_once_with('get_company_facts', args)
            prepare.reset_mock()
            execute_tool('get_company_facts', args)
            prepare.assert_not_called()

class CompanyIndexTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.processed = self.root / 'financial_data/processed'
        self.company = {'ticker': 'ADBE', 'cik': '0000796343'}
        self.report = {**self.company, 'status': 'prepared', 'chunks_path': 'adbe/chunks.json'}
        self.old = {'ticker': 'AAPL', 'cik': '0000320193', 'status': 'prepared'}
        save_yaml({'embedding': {}, 'vector_store': {}}, self.root / 'configs/settings.yaml')
        save_json({'reports': [self.old]}, self.processed / 'filing_preparation_summary.json')
        self.mocks = {}
        targets = {
            'root': ('src.pipeline.prepare_company.ROOT', self.root),
            'collection': ('src.pipeline.prepare_company.get_vector_collection', None),
            'identity': ('src.pipeline.prepare_company.verify_collection_identity', None),
            'filings': ('src.pipeline.prepare_company.process_company_filings', None),
            'embeddings': ('src.pipeline.prepare_company.process_filing_embeddings', None),
            'save': ('src.pipeline.prepare_company.save_embedding_records', None),
        }
        for name, (target, value) in targets.items():
            patcher = patch(target, value) if name == 'root' else patch(target)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        self.collection = self.mocks['collection'].return_value
        self.collection.metadata = {'ready': True}
        self.collection.get.return_value = {'ids': ['old-adbe'], 'documents': ['old'], 'metadatas': [{}]}
        self.mocks['identity'].return_value = {'embedding_digest': 'digest'}
        self.mocks['filings'].return_value = [self.report]
        self.mocks['embeddings'].return_value = [{'chunk_id': 'new-adbe'}]

    def test_company_sync_preserves_other_company_reports_and_only_prunes_its_own_ids(self):
        prepare_company_index(self.company, self.processed)
        self.collection.get.assert_called_once_with(where={'cik': self.company['cik']}, include=['documents', 'metadatas'])
        self.collection.delete.assert_called_once_with(ids=['old-adbe'])
        summary = load_json(self.processed / 'filing_preparation_summary.json')
        self.assertEqual(summary['reports'], [self.old, self.report])
        self.assertTrue(self.collection.modify.call_args.kwargs['metadata']['ready'])

    def test_embedding_failure_does_not_publish_partial_company_index(self):
        self.mocks['embeddings'].side_effect = ValueError('Embedding unavailable')
        with self.assertRaisesRegex(ValueError, 'Embedding unavailable'):
            prepare_company_index(self.company, self.processed)
        self.mocks['save'].assert_not_called()
        self.collection.modify.assert_not_called()
        self.collection.delete.assert_not_called()
