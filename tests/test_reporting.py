import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.reporting import DISCLAIMER, build_report, format_citation_links, save_report, source_financial_rows, split_research_note
from src.verification.agent_answer import build_fact_catalog, compose_template, render_agent_template


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.result = {
            "answer": "AAPL revenue: 416161000000 USD [Source 1]",
            "verification": {"supported": True},
            "evidence": [{"source_id": 1, "tool": "get_company_facts", "result": {
                "company": {"ticker": "AAPL"},
                "records": [{"form": "10-K", "accn": "0000320193-25-000079"}],
            }}],
        }

    def test_sources_and_required_footer_are_preserved(self):
        note = build_report("Revenue?", self.result)
        self.assertIn("416161000000 USD", note)
        self.assertIn("0000320193-25-000079", note)
        self.assertIn("[^1]: AAPL | 10-K", note)
        self.assertIn("416161000000 USD [^1]", note)
        self.assertTrue(note.endswith(DISCLAIMER + "\n"))

    def test_citation_links_preserve_positions_and_multi_digit_ids(self):
        text = "Revenue [Source 2].\n\nCosts [Source 12]. Risk [Source 2]."
        self.assertEqual(format_citation_links(text),
                         "Revenue [²](#source-2).\n\nCosts [¹²](#source-12). Risk [²](#source-2).")

    def test_only_exact_generated_supporting_records_are_collapsed(self):
        evidence = self.result["evidence"]
        composition = {"kind": "answer", "text": "Reported in {{1:records/0/form}}. [Source 1]",
                       "facts": ["1:records/0"]}
        catalog = build_fact_catalog(evidence)
        answer = render_agent_template(compose_template(composition, catalog), evidence)
        result = {**self.result, "composition": composition, "answer": answer}
        prose, details = split_research_note(result)
        self.assertEqual(prose, "Reported in 10-K. [Source 1]")
        self.assertIn("AAPL | 10-K", details)
        self.assertEqual(prose + "\n\n" + details, answer)
        note = build_report("Explain [Source 99]", result)
        self.assertIn("Explain [Source 99]", note)  # Preserve the original question.
        self.assertIn("Reported in 10-K. [^1]", note)
        self.assertIn("<details>", note)
        self.assertIn("[^1]: AAPL", note)
        altered = {**result, "answer": answer + "\nExtra statement."}
        self.assertEqual(split_research_note(altered), (altered["answer"], ""))
        self.assertEqual(result["answer"], answer)

    def test_facts_only_answer_remains_visible(self):
        composition = {"kind": "answer", "text": "", "facts": ["1:records/0"]}
        evidence = self.result["evidence"]
        answer = render_agent_template(compose_template(composition, build_fact_catalog(evidence)), evidence)
        self.assertEqual(split_research_note({**self.result, "answer": answer, "composition": composition}),
                         (answer, ""))

    def test_unverified_drafts_cannot_be_exported(self):
        for result in ({"answer": "Unverified"}, {**self.result, "verification": {"supported": False}},
                       {**self.result, "answer": None}):
            with self.subTest(result=result), self.assertRaises(ValueError):
                build_report("Question", result)

    def test_partial_financial_rows_use_completed_tools_not_rejected_draft(self):
        record = {"metric": "revenue", "value": 123, "unit": "USD", "fiscal_year": 2026,
                  "end": "2026-06-30", "form": "10-K", "tag": "RevenueTag"}
        event = {"type": "tool", "status": "completed", "name": "get_company_facts",
                 "arguments": {}, "result": {"company": {"ticker": "MSFT"}, "records": [record]}}
        result = {"answer": None, "draft": "Revenue was 999 USD", "trace": [
            {**event, "status": "failed"}, event,
        ], "verification": {"supported": False}}
        rows, evidence = source_financial_rows(result)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Değer"], 123)
        self.assertEqual(rows[0]["Etiket"], "RevenueTag")
        self.assertEqual(rows[0]["Kaynak"], 1)
        self.assertEqual(evidence[0]["result"]["records"][0], record)
        with self.assertRaises(ValueError):
            build_report("Revenue?", result)

    def test_empty_trace_does_not_inherit_stale_financial_evidence(self):
        rows, evidence = source_financial_rows({**self.result, "trace": []})
        self.assertEqual((rows, evidence), ([], []))

    def test_exports_create_distinct_files_only_in_reports(self):
        with tempfile.TemporaryDirectory() as directory, patch("src.reporting.PROJECT_ROOT", Path(directory)):
            first = save_report("../outside", self.result)
            original = first.read_text()
            second = save_report("Question", self.result)
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, Path(directory) / "reports")
            self.assertEqual(first.read_text(), original)
            self.assertEqual(set(Path(directory).iterdir()), {first.parent})

    def test_reports_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            (Path(directory) / "reports").symlink_to(outside, target_is_directory=True)
            with patch("src.reporting.PROJECT_ROOT", Path(directory)), self.assertRaises(ValueError):
                save_report("Question", self.result)
            self.assertEqual(list(Path(outside).iterdir()), [])
