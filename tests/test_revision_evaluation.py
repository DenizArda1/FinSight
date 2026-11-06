import unittest

from eval.diagnostics.run_revision_controls import score_controls


class RevisionEvaluationTests(unittest.TestCase):
    def test_errors_are_not_counted_as_correct_rejections(self):
        rows = [
            {"mode": "full", "expected_supported": False,
             "verification": {"status": "error", "supported": False}},
            {"mode": "full", "expected_supported": False,
             "verification": {"status": "passed", "supported": True}},
            {"mode": "paragraph", "expected_supported": True,
             "verification": {"status": "failed", "supported": False}},
            {"mode": "paragraph", "expected_supported": False,
             "verification": {"status": "failed", "supported": False}},
        ]
        self.assertEqual(score_controls(rows), {
            "full": {"correct": 0, "false_accept": 1, "false_reject": 0, "error": 1},
            "paragraph": {"correct": 1, "false_accept": 0, "false_reject": 1, "error": 0},
        })
