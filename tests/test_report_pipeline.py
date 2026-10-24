import unittest
from unittest.mock import patch

from src.pipeline.run_report_context_pipeline import answer_report_question


class ReportPipelineTests(unittest.TestCase):
    def setUp(self):
        self.matches = [{
            "chunk_id": "report:1",
            "text": "Export restrictions may affect sales.",
            "metadata": {
                "ticker": "NVDA", "fiscal_year": 2026, "section": "Item 1A",
                "form": "10-K", "report_date": "2026-01-25", "accession_number": "report",
                "source_url": "https://example.com/report",
            },
            "distance": 0.2,
        }]
        self.config = {"model": "test-model"}
        search_patcher = patch(
            "src.pipeline.run_report_context_pipeline.search_company_reports",
            return_value={"matches": self.matches},
        )
        config_patcher = patch(
            "src.pipeline.run_report_context_pipeline.load_yaml",
            return_value={"llm": self.config},
        )
        generate_patcher = patch(
            "src.pipeline.run_report_context_pipeline.generate_response",
            return_value="Sales may be affected [Source 1].",
        )
        self.search = search_patcher.start()
        self.addCleanup(search_patcher.stop)
        self.load_config = config_patcher.start()
        self.addCleanup(config_patcher.stop)
        self.generate = generate_patcher.start()
        self.addCleanup(generate_patcher.stop)
        self.verification = {"supported": True, "issues": []}
        verify_patcher = patch(
            "src.pipeline.run_report_context_pipeline.verify_report_answer",
            return_value=self.verification,
        )
        self.verify = verify_patcher.start()
        self.addCleanup(verify_patcher.stop)

    def test_filters_and_sources_reach_answer_generation(self):
        result = answer_report_question("NVDA", "What risks?", fiscal_year=2026, section="Item 1A", top_k=3)

        self.search.assert_called_once_with(
            ticker="NVDA", query="What risks?", fiscal_year=2026, section="Item 1A", top_k=3,
        )
        self.generate.assert_called_once()
        messages, config = self.generate.call_args.args
        self.assertEqual(config, self.config)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1], {
            "role": "user",
            "content": (
                "Question:\nWhat risks?\n\nSources:\n"
                "[Source 1]\nCompany: NVDA\nForm: 10-K\nFiscal year: FY2026 (period end: 2026-01-25)\n"
                "Accession: report\nSection: Item 1A\nURL: https://example.com/report\n"
                "<filing_excerpt>\nExport restrictions may affect sales.\n</filing_excerpt>"
            ),
        })
        self.verify.assert_called_once_with(
            "What risks?",
            "Sales may be affected [Source 1].",
            "[Source 1]\nCompany: NVDA\nForm: 10-K\nFiscal year: FY2026 (period end: 2026-01-25)\n"
            "Accession: report\nSection: Item 1A\nURL: https://example.com/report\n"
            "<filing_excerpt>\nExport restrictions may affect sales.\n</filing_excerpt>",
            self.config,
        )
        self.assertEqual(result, {
            "answer": "Sales may be affected [Source 1].", "matches": self.matches,
            "verification": self.verification,
        })

    def test_no_sources_skip_configuration_and_llm_call(self):
        self.search.return_value = {"matches": []}

        self.assertEqual(answer_report_question("NVDA", "What risks?"), {
            "answer": None, "matches": [], "verification": None,
        })
        self.generate.assert_not_called()
        self.load_config.assert_not_called()
        self.verify.assert_not_called()

    def test_generation_and_verification_receive_same_expanded_context(self):
        expanded_text = "Restrictions on exports may affect sales. <Untrusted source text>"
        self.matches[0]["context"] = {"text": expanded_text, "start": 0, "end": len(expanded_text)}
        result = answer_report_question("NVDA", "What risks?")
        source_context = self.verify.call_args.args[2]
        self.assertIn("Restrictions on exports", source_context)
        self.assertIn("&lt;Untrusted source text&gt;", source_context)
        self.assertEqual(self.generate.call_args.args[0][1]["content"],
                         "Question:\nWhat risks?\n\nSources:\n" + source_context)
        self.assertEqual(result["matches"][0]["text"], "Export restrictions may affect sales.")

    def test_generation_failure_is_propagated(self):
        self.generate.side_effect = ValueError("LLM response content must be a non-empty string")
        with self.assertRaisesRegex(ValueError, "non-empty string"):
            answer_report_question("NVDA", "What risks?")
        self.verify.assert_not_called()

    def test_unsupported_answer_is_withheld_but_sources_and_issues_are_preserved(self):
        verification = {"supported": False, "issues": ["The claim about taxes is unsupported."]}
        self.verify.return_value = verification

        result = answer_report_question("NVDA", "What risks?")

        self.assertEqual(result, {
            "answer": None, "matches": self.matches, "verification": verification,
        })

    def test_invalid_citations_stop_before_verification(self):
        for answer in ("No citations.", "Claim [Source 2]."):
            self.generate.return_value = answer
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                answer_report_question("NVDA", "What risks?")
        self.verify.assert_not_called()

    def test_verification_failure_does_not_return_an_unchecked_answer(self):
        self.verify.side_effect = ValueError("Verification response must be a JSON object")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            answer_report_question("NVDA", "What risks?")


if __name__ == "__main__":
    unittest.main()
