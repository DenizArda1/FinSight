import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.tools.financial_metrics import get_company_facts, compute_metrics
from src.agents.specialist import scoped_tool_arguments
from src.utils.utils import save_json, save_yaml


class HistoricalFinancialTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.cik = '0000000042'
        patcher = patch('src.tools.financial_metrics.PROJECT_ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        save_yaml({'metrics': {'revenue': {'unit': 'USD'}}}, self.root / 'configs/metrics.yaml')
        ends = ['2026-01-25', '2025-01-26', '2024-01-28']
        save_json({'cik': self.cik, 'ticker': 'TEST', 'name': 'Test',
                   'filings': [{'form': '10-K', 'reportDate': end} for end in ends]},
                  self.root / 'financial_data/raw' / self.cik / 'manifest.json')
        save_json([{'cik': 42, 'metric': 'revenue', 'unit': 'USD', 'end': end,
                    'fiscal_year': year, 'value': year} for end, year in zip(ends, [2026, 2025, 2024])],
                  self.root / 'financial_data/processed' / self.cik / 'revenue.json')

    def test_explicit_fiscal_year_anchors_window_instead_of_latest(self):
        result = get_company_facts(self.cik, 'revenue', years=2, fiscal_year=2025)
        self.assertEqual([r['fiscal_year'] for r in result['records']], [2025, 2024])
        self.assertEqual(get_company_facts(self.cik, 'revenue', years=1)['records'][0]['fiscal_year'], 2026)

    def test_missing_year_does_not_fall_back_to_latest(self):
        result = get_company_facts(self.cik, 'revenue', years=1, fiscal_year=2020)
        self.assertEqual(result['records'], [])
        self.assertFalse(result['history_complete'])
        for value in (True, '2025', 2025.0, 0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                get_company_facts(self.cik, 'revenue', fiscal_year=value)

    def test_specialist_preserves_explicit_year_for_both_financial_tools(self):
        for name in ('get_company_facts', 'compute_metrics'):
            args = {'years': 1}
            result = scoped_tool_arguments(name, args, 'annual', 1, 2025)
            self.assertEqual(result, {'years': 1, 'fiscal_year': 2025})
            self.assertEqual(args, {'years': 1})
