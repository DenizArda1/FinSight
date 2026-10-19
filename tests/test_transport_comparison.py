from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eval.compare_transports import compare_results
from eval.snapshots import capture_snapshot


def comparison_row():
    return {
        'id': 'case', 'question': 'Question', 'expected': {'value': 1},
        'dataset_sha256': 'questions', 'llm_config': {'model': 'model', 'options': {'seed': 0}},
        'data_snapshot': {'source_sha256': 'data', 'index_sha256': 'index'},
        'status': 'completed', 'verification': {'status': 'passed'}, 'answer': 'Answer',
        'trace': [{'type': 'tool', 'name': 'get_company_facts', 'status': 'completed',
                   'result': {'records': [{'value': 1}]}}],
        'elapsed_seconds': 1,
    }


class TransportComparisonTests(unittest.TestCase):
    def test_two_withheld_answers_are_not_counted_as_matching_answer_text(self):
        direct, mcp = comparison_row(), comparison_row()
        direct['answer'] = mcp['answer'] = None
        direct['status'] = mcp['status'] = 'withheld'
        row = compare_results([direct], [mcp])[0]
        self.assertTrue(row['same_status'])
        self.assertIsNone(row['exact_answer_match'])

    def test_text_difference_is_separate_from_tool_and_verification_equality(self):
        direct = comparison_row()
        mcp = deepcopy(direct)
        mcp['answer'] = 'A differently worded answer'
        result = compare_results([direct], [mcp])[0]
        self.assertTrue(result['same_successful_tool_payloads'])
        self.assertTrue(result['same_status'])
        self.assertFalse(result['exact_answer_match'])
        self.assertIsNone(result['manual_review'])

    def test_mismatched_inputs_and_case_ids_are_rejected(self):
        for key in ('id', 'question', 'expected', 'dataset_sha256', 'llm_config', 'data_snapshot'):
            with self.subTest(key=key):
                direct, mcp = comparison_row(), comparison_row()
                mcp[key] = 'different'
                with self.assertRaises(ValueError):
                    compare_results([direct], [mcp])

    def test_source_fingerprint_is_stable_and_changes_with_data(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'financial_data/processed'
            data.mkdir(parents=True)
            (data / 'facts.json').write_text('{"value": 1}')
            first = capture_snapshot(root, {})
            self.assertEqual(first, capture_snapshot(root, {}))
            (data / 'facts.json').write_text('{"value": 2}')
            self.assertNotEqual(first['source_sha256'], capture_snapshot(root, {})['source_sha256'])


if __name__ == '__main__':
    unittest.main()
