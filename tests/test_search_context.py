from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.tools.report_search import expand_search_matches, search_company_reports
from src.utils.utils import save_json


class SearchContextTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.processed = self.root / "financial_data" / "processed"
        self.company = {"ticker": "TEST", "cik": "0000000001", "name": "Test Company"}
        self.accession = "0000000001-25-000001"
        self.directory = self.processed / self.company["cik"] / "filings" / self.accession
        self.section_text = "Failure to obtain licenses may prevent sales. Further risks follow."
        self.document = {
            "company": self.company,
            "filing": {"accessionNumber": self.accession, "fiscal_year": 2025,
                       "reportDate": "2025-12-31", "form": "10-K", "url": "https://example.com/report"},
            "text": "INTRO|" + self.section_text + "|NEXT SECTION",
        }
        self.sections = [{"section": "Item 1A", "start": 6,
                          "end": 6 + len(self.section_text), "text": self.section_text}]
        text = "prevent sales."
        start = self.document["text"].index(text)
        self.match = {
            "chunk_id": self.accession + ":item_1a:0", "text": text, "distance": 0.1,
            "metadata": {
                "ticker": "TEST", "cik": self.company["cik"], "accession_number": self.accession,
                "fiscal_year": 2025, "report_date": "2025-12-31", "form": "10-K",
                "source_url": "https://example.com/report", "section": "Item 1A",
                "start": start, "end": start + len(text),
                "section_start": 6, "section_end": 6 + len(self.section_text),
            },
        }
        save_json(self.document, self.directory / "text.json")
        save_json(self.sections, self.directory / "sections.json")

    def test_search_attaches_verified_context_and_preserves_ranking_and_chunks(self):
        second = {**deepcopy(self.match), "chunk_id": self.accession + ":item_1a:1", "distance": 0.2}
        matches = [self.match, second]
        original = deepcopy(matches)
        with patch("src.tools.report_search.PROJECT_ROOT", self.root), patch(
            "src.tools.report_search.resolve_company", return_value=self.company
        ), patch("src.tools.report_search.load_yaml", return_value={"embedding": {}, "vector_store": {}}), patch(
            "src.tools.report_search.get_vector_collection"
        ), patch("src.tools.report_search.search_reports", return_value=matches):
            result = search_company_reports("TEST", "What risks?", section="Item 1A")

        self.assertEqual(matches, original)
        for expanded, source in zip(result["matches"], original):
            self.assertEqual({key: value for key, value in expanded.items() if key != "context"}, source)
            self.assertEqual(expanded["context"], {
                "text": self.section_text, "start": 6, "end": 6 + len(self.section_text),
            })

    def test_empty_results_do_not_load_files(self):
        with patch("src.tools.report_search.load_json") as load:
            self.assertEqual(expand_search_matches([], self.processed), [])
        load.assert_not_called()

    def test_missing_files_raise_instead_of_returning_unexpanded_chunks(self):
        for filename in ("text.json", "sections.json"):
            with self.subTest(filename=filename):
                path = self.directory / filename
                contents = path.read_text()
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    expand_search_matches([self.match], self.processed)
                path.write_text(contents)

    def test_stale_chunk_or_section_bounds_are_rejected(self):
        cases = [
            {**self.match, "text": "Changed indexed text"},
            {**self.match, "metadata": {**self.match["metadata"], "section_start": 0}},
            {**self.match, "metadata": {**self.match["metadata"], "form": "10-K/A"}},
        ]
        for match in cases:
            with self.subTest(match=match), self.assertRaises(ValueError):
                expand_search_matches([match], self.processed)

    def test_corrupt_prepared_section_is_rejected(self):
        save_json([{**self.sections[0], "text": "Different report text"}], self.directory / "sections.json")
        with self.assertRaisesRegex(ValueError, "report text"):
            expand_search_matches([self.match], self.processed)


if __name__ == "__main__":
    unittest.main()
