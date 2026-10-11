import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import call, patch

from src.finsight.pipeline.run_filing_pipeline import main, process_latest_filing, process_company_filings
from tests.filing_fixtures import make_report, REPORT_TEXT


class FilingPipelineTests(unittest.TestCase):
    def setUp(self):
        self.report = make_report()

    def test_successful_pipeline_saves_matching_text_and_source_linked_chunks(self):
        with patch("src.finsight.pipeline.run_filing_pipeline.load_latest_filing", return_value=self.report), patch(
            "src.finsight.pipeline.run_filing_pipeline.save_json"
        ) as save:
            document = process_latest_filing("AAPL")

        self.assertEqual(document["text"], REPORT_TEXT)
        self.assertEqual(document["company"], self.report["company"])
        self.assertEqual(document["filing"]["fiscal_year"], 2025)
        self.assertEqual(save.call_count, 3)
        saved_document, text_path = save.call_args_list[0].args
        saved_chunks, chunks_path = save.call_args_list[2].args
        self.assertEqual(saved_document["text"], document["text"])
        self.assertEqual(save.call_args_list[1].args[0], document["sections"])
        self.assertEqual(text_path.name, "text.json")
        self.assertEqual(chunks_path.name, "chunks.json")
        self.assertEqual(text_path.parent, chunks_path.parent)
        self.assertTrue(str(text_path).endswith("0000320193/filings/test-accession/text.json"))
        self.assertEqual({chunk["metadata"]["section"] for chunk in saved_chunks}, {"Item 1", "Item 1A", "Item 7"})
        for chunk in saved_chunks:
            metadata = chunk["metadata"]
            self.assertEqual(chunk["text"], document["text"][metadata["start"]:metadata["end"]])
            self.assertLessEqual(metadata["end"], metadata["section_end"])
        self.assertEqual(saved_chunks[0]["metadata"]["source_url"], self.report["filing"]["url"])

    def test_empty_visible_text_is_rejected_without_writing(self):
        self.report["html"] = "<head><title>Title</title></head><script>code()</script><div hidden>Hidden</div>"
        with patch("src.finsight.pipeline.run_filing_pipeline.load_latest_filing", return_value=self.report), patch(
            "src.finsight.pipeline.run_filing_pipeline.build_document_chunks"
        ) as build, patch("src.finsight.pipeline.run_filing_pipeline.save_json") as save:
            with self.assertRaisesRegex(ValueError, "No visible report text found for AAPL"):
                process_latest_filing("AAPL")

        build.assert_not_called()
        save.assert_not_called()

    def test_chunk_failure_does_not_write_any_output(self):
        with patch("src.finsight.pipeline.run_filing_pipeline.load_latest_filing", return_value=self.report), patch(
            "src.finsight.pipeline.run_filing_pipeline.build_document_chunks",
            side_effect=ValueError("Chunk position error"),
        ), patch("src.finsight.pipeline.run_filing_pipeline.save_json") as save:
            with self.assertRaisesRegex(ValueError, "Chunk position error"):
                process_latest_filing("AAPL")

        save.assert_not_called()

    def test_empty_chunk_list_is_rejected_without_writing(self):
        with patch("src.finsight.pipeline.run_filing_pipeline.load_latest_filing", return_value=self.report), patch(
            "src.finsight.pipeline.run_filing_pipeline.build_document_chunks", return_value=[]
        ), patch("src.finsight.pipeline.run_filing_pipeline.save_json") as save:
            with self.assertRaisesRegex(ValueError, "No text chunks produced for AAPL"):
                process_latest_filing("AAPL")

        save.assert_not_called()

    def test_report_loading_failure_does_not_write_any_output(self):
        with patch("src.finsight.pipeline.run_filing_pipeline.load_latest_filing", side_effect=FileNotFoundError("Missing report")), patch(
            "src.finsight.pipeline.run_filing_pipeline.save_json"
        ) as save:
            with self.assertRaises(FileNotFoundError):
                process_latest_filing("AAPL")

        save.assert_not_called()

    def test_missing_section_does_not_write_any_output(self):
        self.report["html"] = self.report["html"].replace("Item 1A. Risk Factors", "Risks")
        with patch("src.finsight.pipeline.run_filing_pipeline.load_latest_filing", return_value=self.report), patch(
            "src.finsight.pipeline.run_filing_pipeline.save_json"
        ) as save:
            with self.assertRaisesRegex(ValueError, "Expected one substantive"):
                process_latest_filing("AAPL")
        save.assert_not_called()

    def test_missing_fiscal_year_does_not_write_any_output(self):
        self.report["html"] = self.report["html"].replace("dei:DocumentFiscalYearFocus", "dei:OtherFact")
        with patch("src.finsight.pipeline.run_filing_pipeline.load_latest_filing", return_value=self.report), patch(
            "src.finsight.pipeline.run_filing_pipeline.save_json"
        ) as save:
            with self.assertRaisesRegex(ValueError, "DocumentFiscalYearFocus"):
                process_latest_filing("AAPL")
        save.assert_not_called()


class FilingCommandTests(unittest.TestCase):
    def test_tickers_are_normalized_and_processed_once(self):
        with patch("src.finsight.pipeline.run_filing_pipeline.process_company_filings", return_value=[]) as process, patch(
            "src.finsight.pipeline.run_filing_pipeline.save_json"
        ), redirect_stdout(io.StringIO()):
            main(["--tickers", " aapl,MSFT,aapl, "])
        self.assertEqual(process.call_args_list, [call("AAPL", 5, 1500, 200), call("MSFT", 5, 1500, 200)])

    def test_invalid_arguments_are_rejected_before_processing(self):
        for args in (["--tickers", " , "], ["--years", "0"], ["--max-chars", "200", "--overlap", "200"]):
            with self.subTest(args=args), patch("src.finsight.pipeline.run_filing_pipeline.process_company_filings") as process, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(args)
            self.assertEqual(error.exception.code, 2)
            process.assert_not_called()

    def test_company_failure_is_logged_and_next_company_is_processed(self):
        with patch("src.finsight.pipeline.run_filing_pipeline.process_company_filings", side_effect=[ValueError("Empty report"), []]) as process, patch(
            "src.finsight.pipeline.run_filing_pipeline.save_json"
        ) as save, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(["--tickers", "AAPL,MSFT"])
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(process.call_count, 2)
        summary = save.call_args.args[0]
        self.assertEqual(summary["company_errors"], [{"ticker": "AAPL", "error": "Empty report"}])

    def test_failed_report_does_not_prevent_processing_next_report(self):
        report = make_report()
        filings = [report["filing"], {**report["filing"], "accessionNumber": "next-accession"}]
        document = {"filing": {"fiscal_year": 2025}, "sections": [{}, {}, {}], "chunk_count": 3, "preparation": {}}
        with patch("src.finsight.pipeline.run_filing_pipeline.select_filings", return_value={"company": report["company"], "filings": filings}), patch(
            "src.finsight.pipeline.run_filing_pipeline.load_filing", side_effect=[FileNotFoundError("Missing report"), report]
        ), patch("src.finsight.pipeline.run_filing_pipeline.process_filing", return_value=document):
            results = process_company_filings("AAPL")
        self.assertEqual([entry["status"] for entry in results], ["failed", "prepared"])
        self.assertEqual(results[0]["error"], "Missing report")
        self.assertNotIn("chunks_path", results[0])
        self.assertIn("next-accession", results[1]["chunks_path"])


if __name__ == "__main__":
    unittest.main()
