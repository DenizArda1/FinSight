import json
import unittest
from unittest.mock import patch

from src.agents.agent_states import create_initial_state
from src.agents.coverage import check_coverage
from src.verification.agent_answer import build_fact_catalog, compose_template, render_agent_template


class CoverageTests(unittest.IsolatedAsyncioTestCase):
    @patch('src.agents.coverage.request_answer_check')
    async def test_missing_period_can_request_generic_repair(self, request):
        state = create_initial_state('Compare Example Corp revenue with last year.')
        task = {'id': 'gap', 'agent': 'financial_data', 'instruction': 'Resolve Example Corp; compute revenue_growth, years=2.',
                'fiscal_year': None, 'filing_scope': 'annual', 'years': 2}
        request.return_value = json.dumps({'complete': False, 'gaps': ['Previous-year growth missing.'], 'tasks': [task]})
        result = await check_coverage(state, {})
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['tasks'][0]['years'], 2)
        self.assertEqual(request.call_args.args[3], 'coverage')

    @patch('src.agents.coverage.request_answer_check')
    async def test_unknown_or_invalid_review_is_not_complete(self, request):
        for response in ('not JSON', json.dumps({'complete': True, 'gaps': ['Missing data'], 'tasks': []})):
            request.return_value = response
            result = await check_coverage(create_initial_state('Question'), {})
            self.assertEqual(result['status'], 'unknown')
            self.assertFalse(result['complete'])

    def test_localized_dates_bind_only_to_the_cited_record(self):
        evidence = [{'source_id': 1, 'tool': 'get_company_facts', 'result': {'records': [
            {'value': 200, 'unit': 'USD', 'end': '2025-05-31', 'fiscal_year': 2025}]}}]
        catalog = build_fact_catalog(evidence)
        for label in ('31 Mayıs 2025', '31 Mayıs 2025’te', '31 May 2025', 'May 31, 2025'):
            payload = {'kind': 'answer', 'text': label + ' dönem sonu. [Source 1]', 'facts': []}
            self.assertIn('2025-05-31', render_agent_template(compose_template(payload, catalog), evidence))
        for label in ('31 Mayıs 2024', '30 Mayıs 2025', '200 USD'):
            with self.subTest(label=label), self.assertRaises(ValueError):
                render_agent_template(compose_template({'kind': 'answer', 'text': label + ' [Source 1]', 'facts': []}, catalog), evidence)

    def test_quarter_labels_require_exact_cited_report_support(self):
        evidence = [{'source_id': 1, 'tool': 'search_company_updates', 'result': {
            'matches': [{'text': 'Q3 2026 revenue increased. Q4 2026 outlook.', 'metadata': {}}]}}]
        catalog = build_fact_catalog(evidence)
        for text in ('Q3 2026 results. [Source 1]', 'Q4 2026 outlook. [Source 1]'):
            self.assertIn(text, render_agent_template(compose_template({'kind': 'answer', 'text': text, 'facts': []}, catalog), evidence))
        for text in ('Q2 2026 results.', 'Q3 2025 results.', '100 USD revenue.'):
            with self.assertRaises(ValueError):
                render_agent_template(compose_template({'kind': 'answer', 'text': text + ' [Source 1]', 'facts': []}, catalog), evidence)

    def test_cited_digit_leading_product_name_does_not_exempt_amounts(self):
        evidence = [{'source_id': 1, 'tool': 'search_filings', 'result': {'matches': [
            {'text': 'Intel 14A development. Revenue 100USD and 20M.', 'metadata': {}}]}}]
        catalog = build_fact_catalog(evidence)
        payload = {'kind': 'answer', 'text': 'Intel 14A development. [Source 1]', 'facts': []}
        self.assertIn('Intel 14A', render_agent_template(compose_template(payload, catalog), evidence))
        for token in ('18A', '100USD', '20M'):
            with self.assertRaises(ValueError):
                render_agent_template(compose_template({**payload, 'text': token + ' [Source 1]'}, catalog), evidence)
