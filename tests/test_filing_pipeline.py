import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import call, patch

from src.finsight.pipeline.run_filing_pipeline import main, process_latest_filing


class FilingPipelineTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "company": {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193"},
            "filing": {
                "accessionNumber": "test-accession",
                "reportDate": "2025-09-27",
                "url": "https://example.invalid/report",
            },
            "html": "<p>Revenue <span>100</span> dollars.</p>",
        }

    def test_successful_pipeline_saves_matching_text_and_source_linked_chunks(self):
        with patch("src.finsight.pipeline.run_filing_pipeline.load_latest_filing", return_value=self.report), patch(
            "src.finsight.pipeline.run_filing_pipeline.save_json"
        ) as save:
            document = process_latest_filing("AAPL")

        self.assertEqual(document["text"], "Revenue 100 dollars.")
        self.assertEqual(document["company"], self.report["company"])
        self.assertEqual(document["filing"], self.report["filing"])
        self.assertEqual(save.call_count, 2)
        saved_document, text_path = save.call_args_list[0].args
        saved_chunks, chunks_path = save.call_args_list[1].args
        self.assertEqual(saved_document, document)
        self.assertEqual(text_path.name, "text.json")
        self.assertEqual(chunks_path.name, "chunks.json")
        self.assertEqual(text_path.parent, chunks_path.parent)
        self.assertTrue(str(text_path).endswith("0000320193/filings/test-accession/text.json"))
        self.assertEqual(saved_chunks[0]["text"], document["text"])
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


class FilingCommandTests(unittest.TestCase):
    def test_tickers_are_normalized_and_processed_once(self):
        document = {"filing": {"reportDate": "2025-09-27"}}
        with patch("src.finsight.pipeline.run_filing_pipeline.process_latest_filing", return_value=document) as process, redirect_stdout(io.StringIO()):
            main(["--tickers", " aapl,MSFT,aapl, "])

        self.assertEqual(process.call_args_list, [call("AAPL"), call("MSFT")])

    def test_empty_ticker_list_is_rejected(self):
        with patch("src.finsight.pipeline.run_filing_pipeline.process_latest_filing") as process, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(["--tickers", " , "])

        self.assertEqual(error.exception.code, 2)
        process.assert_not_called()

    def test_processing_failure_returns_nonzero_exit_with_company_name(self):
        stderr = io.StringIO()
        with patch("src.finsight.pipeline.run_filing_pipeline.process_latest_filing", side_effect=ValueError("Empty report")), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as error:
                main(["--tickers", "AAPL"])

        self.assertEqual(error.exception.code, 1)
        self.assertIn("AAPL: Empty report", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
