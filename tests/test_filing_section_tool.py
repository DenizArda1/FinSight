from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.tools.dispatcher import execute_tool
from src.tools.report_search import get_filing_section, load_match_document
from src.utils.utils import save_json
from src.verification.agent_answer import build_agent_evidence, build_fact_catalog, format_source_references


class FilingSectionToolTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        root_patch = patch('src.tools.report_search.PROJECT_ROOT', self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.company = {'ticker': 'TEST', 'cik': '0000000001', 'name': 'Test Company'}
        company_patch = patch('src.tools.report_search.resolve_company', return_value=self.company)
        company_patch.start()
        self.addCleanup(company_patch.stop)
        self.accession = '0000000001-25-000001'
        self.url = 'https://example.com/report.htm'
        self.directory = self.root / 'financial_data/processed/0000000001/filings' / self.accession
        self.summary_path = self.root / 'financial_data/processed/filing_preparation_summary.json'
        self.entry = {
            'cik': self.company['cik'], 'ticker': 'TEST', 'fiscal_year': 2025,
            'accession_number': self.accession, 'report_date': '2024-12-28',
            'source_url': self.url, 'status': 'prepared',
        }
        self.text = 'Item 1A. Risks\n' + 'A full source paragraph.\n' * 3000
        self.document = {
            'company': self.company,
            'filing': {'accessionNumber': self.accession, 'fiscal_year': 2025,
                       'reportDate': '2024-12-28', 'url': self.url, 'form': '10-K'},
            'text': 'Intro\n' + self.text + 'Next section',
        }
        self.sections = [{'section': 'Item 1A', 'title': 'Risk Factors',
                          'start': 6, 'end': 6 + len(self.text), 'text': self.text}]
        save_json({'reports': [self.entry]}, self.summary_path)
        save_json(self.document, self.directory / 'text.json')
        save_json(self.sections, self.directory / 'sections.json')

    def test_match_loads_exact_report_without_changing_input(self):
        match = {'metadata': {**self.entry, 'form': '10-K'}}
        original = deepcopy(match)
        document = load_match_document(match, self.root / 'financial_data/processed')
        self.assertEqual(document, self.document)
        self.assertEqual(match, original)

    def test_invalid_match_metadata_is_rejected_before_reading(self):
        metadata = {**self.entry, 'form': '10-K'}
        invalid = [None, [], {}, {'metadata': []}]
        for changes in ({'cik': '../escape'}, {'cik': 1}, {'cik': '1'},
                        {'accession_number': '../escape'}, {'accession_number': None},
                        {'ticker': ''}, {'form': None}, {'report_date': ''},
                        {'source_url': None}, {'fiscal_year': True}, {'fiscal_year': 0}):
            invalid.append({'metadata': {**metadata, **changes}})
        with patch('src.tools.report_search.load_json') as load:
            for match in invalid:
                with self.subTest(match=match), self.assertRaises(ValueError):
                    load_match_document(match, self.root / 'financial_data/processed')
            load.assert_not_called()

    def test_match_report_identity_and_metadata_mismatches_are_rejected(self):
        match = {'metadata': {**self.entry, 'form': '10-K'}}
        changes = (
            ('company', 'cik', '0000000002'), ('company', 'ticker', 'OTHER'),
            ('filing', 'accessionNumber', '0000000001-24-000001'),
            ('filing', 'fiscal_year', 2024), ('filing', 'fiscal_year', True),
            ('filing', 'form', '10-K/A'), ('filing', 'reportDate', '2024-12-31'),
            ('filing', 'url', 'https://example.com/other.htm'),
        )
        for group, field, value in changes:
            with self.subTest(field=field, value=value):
                document = deepcopy(self.document)
                document[group][field] = value
                save_json(document, self.directory / 'text.json')
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    load_match_document(match, self.root / 'financial_data/processed')

    def test_malformed_prepared_report_is_rejected(self):
        match = {'metadata': {**self.entry, 'form': '10-K'}}
        for document in ([], {}, {**self.document, 'company': []},
                         {**self.document, 'filing': None},
                         {**self.document, 'text': ' '}, {**self.document, 'text': None}):
            with self.subTest(document=document):
                save_json(document, self.directory / 'text.json')
                with self.assertRaises(ValueError):
                    load_match_document(match, self.root / 'financial_data/processed')

    def test_missing_match_report_does_not_fall_back_to_another_report(self):
        match = {'metadata': {**self.entry, 'form': '10-K', 'accession_number': '0000000001-24-000001'}}
        with self.assertRaises(FileNotFoundError):
            load_match_document(match, self.root / 'financial_data/processed')

    def test_complete_text_and_source_metadata_use_reported_fiscal_year(self):
        result = execute_tool('get_filing_section', {'ticker': 'TEST', 'year': 2025, 'section': 'Item 1A'})
        self.assertEqual(result['text'], self.text)
        self.assertGreater(len(result['text']), 60000)
        self.assertEqual(result['metadata']['fiscal_year'], 2025)
        self.assertEqual(result['metadata']['report_date'], '2024-12-28')
        self.assertEqual(result['metadata']['source_url'], self.url)
        self.assertEqual(result['metadata']['accession_number'], self.accession)
        with self.assertRaisesRegex(ValueError, 'No prepared filing'):
            get_filing_section('TEST', 2024, 'Item 1A')

    def test_missing_failed_and_ambiguous_reports_do_not_fall_back(self):
        for reports, message in (([], 'No prepared filing'),
                                 ([{**self.entry, 'status': 'failed'}], 'No prepared filing'),
                                 ([self.entry, self.entry], 'ambiguous')):
            with self.subTest(reports=reports):
                save_json({'reports': reports}, self.summary_path)
                with self.assertRaisesRegex(ValueError, message):
                    get_filing_section('TEST', 2025, 'Item 1A')

    def test_missing_sections_and_invalid_offsets_are_rejected(self):
        for sections in ([], self.sections * 2, [{**self.sections[0], 'text': ''}],
                         [{**self.sections[0], 'start': 0}]):
            with self.subTest(sections=bool(sections)):
                save_json(sections, self.directory / 'sections.json')
                with self.assertRaises(ValueError):
                    get_filing_section('TEST', 2025, 'Item 1A')

    def test_identity_and_accession_mismatches_are_rejected(self):
        document = deepcopy(self.document)
        document['company']['cik'] = '0000000002'
        save_json(document, self.directory / 'text.json')
        with self.assertRaisesRegex(ValueError, 'metadata'):
            get_filing_section('TEST', 2025, 'Item 1A')
        save_json({'reports': [{**self.entry, 'accession_number': '../escape'}]}, self.summary_path)
        with self.assertRaisesRegex(ValueError, 'accession'):
            get_filing_section('TEST', 2025, 'Item 1A')

    def test_section_source_is_available_to_answer_verification(self):
        self.text = 'A short complete risk section.'
        self.document['text'] = 'Intro\n' + self.text + 'Next section'
        self.sections[0].update(text=self.text, end=6 + len(self.text))
        save_json(self.document, self.directory / 'text.json')
        save_json(self.sections, self.directory / 'sections.json')
        result = get_filing_section('TEST', 2025, 'Item 1A')
        evidence = build_agent_evidence([{
            'type': 'tool', 'status': 'completed', 'name': 'get_filing_section',
            'arguments': {'ticker': 'TEST', 'year': 2025, 'section': 'Item 1A'}, 'result': result,
        }])
        catalog = build_fact_catalog(evidence)
        self.assertIn('1:metadata', catalog)
        self.assertNotIn('text', catalog['1:metadata']['fields'])
        self.assertIn(self.url, format_source_references('Risk [Source 1]', evidence))
        self.assertEqual(evidence[0]['result']['text'], self.text)

    def test_large_section_tool_stays_complete_but_answer_evidence_is_limited(self):
        result = get_filing_section('TEST', 2025, 'Item 1A')
        evidence = build_agent_evidence([{
            'type': 'tool', 'status': 'completed', 'name': 'get_filing_section',
            'arguments': {'ticker': 'TEST', 'year': 2025, 'section': 'Item 1A'}, 'result': result,
        }])
        self.assertEqual(result['text'], self.text)
        self.assertTrue(evidence[0]['content_omitted'])
        self.assertEqual(build_fact_catalog(evidence), {})
        self.assertNotIn('text', evidence[0]['result'])


if __name__ == '__main__':
    unittest.main()
