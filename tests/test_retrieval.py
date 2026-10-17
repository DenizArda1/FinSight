import unittest
from unittest.mock import Mock, patch

from src.rag.retrieval import format_search_results, search_reports
from src.tools.report_search import search_company_reports


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.collection = Mock()
        self.collection.query.return_value = {
            "ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]],
        }
        self.config = {"model": "test-model"}
        patcher = patch("src.rag.retrieval.embed_text", return_value=[1.0, 0.0])
        self.embed = patcher.start()
        self.addCleanup(patcher.stop)

    def test_all_filter_combinations_are_sent_to_collection(self):
        cases = [
            ({}, None),
            ({"ticker": " nvda "}, {"ticker": "NVDA"}),
            ({"fiscal_year": 2026}, {"fiscal_year": 2026}),
            ({"section": " Item 1A "}, {"section": "Item 1A"}),
            (
                {"ticker": "NVDA", "fiscal_year": 2026},
                {"$and": [{"ticker": "NVDA"}, {"fiscal_year": 2026}]},
            ),
            (
                {"ticker": "NVDA", "section": "Item 1A"},
                {"$and": [{"ticker": "NVDA"}, {"section": "Item 1A"}]},
            ),
            (
                {"fiscal_year": 2026, "section": "Item 1A"},
                {"$and": [{"fiscal_year": 2026}, {"section": "Item 1A"}]},
            ),
            (
                {"ticker": " nvda ", "fiscal_year": 2026, "section": " Item 1A "},
                {"$and": [{"ticker": "NVDA"}, {"fiscal_year": 2026}, {"section": "Item 1A"}]},
            ),
        ]
        for filters, expected_where in cases:
            with self.subTest(filters=filters):
                self.embed.reset_mock()
                self.collection.reset_mock()
                result = search_reports("Export risks?", self.collection, self.config, top_k=3, **filters)
                self.embed.assert_called_once_with("Export risks?", self.config)
                self.collection.query.assert_called_once_with(
                    query_embeddings=[[1.0, 0.0]],
                    n_results=3,
                    where=expected_where,
                    include=["documents", "metadatas", "distances"],
                )
                self.assertEqual(result, [])

    def test_invalid_filters_are_rejected_before_embedding_or_query(self):
        cases = [
            {"section": ""}, {"section": " \n "}, {"section": 1},
            {"section": True}, {"section": []},
            {"ticker": " "}, {"ticker": 1},
            {"fiscal_year": 0}, {"fiscal_year": True}, {"fiscal_year": "2026"},
            {"top_k": 0}, {"top_k": True}, {"top_k": 1.5},
        ]

        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                search_reports("Export risks?", self.collection, self.config, **arguments)
        self.embed.assert_not_called()
        self.collection.query.assert_not_called()

    def test_search_preserves_ranked_results_and_source_metadata(self):
        metadata = [
            {"ticker": "NVDA", "fiscal_year": 2026, "section": "Item 1A",
             "source_url": "https://example.com/nvda-2026", "accession_number": "report-a"},
            {"ticker": "AAPL", "fiscal_year": 2025, "section": "Item 7",
             "source_url": "https://example.com/aapl-2025", "accession_number": "report-b"},
        ]
        self.collection.query.return_value = {
            "ids": [["report-a:1", "report-b:2"]],
            "documents": [["Export restrictions.\nAdditional detail.", "Operating results."]],
            "metadatas": [metadata],
            "distances": [[0.1, 0.4]],
        }
        result = search_reports("Risks?", self.collection, self.config)
        self.assertEqual(result, [
            {"chunk_id": "report-a:1", "text": "Export restrictions.\nAdditional detail.",
             "metadata": metadata[0], "distance": 0.1},
            {"chunk_id": "report-b:2", "text": "Operating results.",
             "metadata": metadata[1], "distance": 0.4},
        ])

    def test_mismatched_result_lengths_are_not_silently_truncated(self):
        with self.assertRaises(ValueError):
            format_search_results({
                "ids": [["a", "b"]], "documents": [["Text"]],
                "metadatas": [[{}]], "distances": [[0.1]],
            })


class ReportSearchToolTests(unittest.TestCase):
    def test_section_is_forwarded_and_matches_are_preserved(self):
        company = {"ticker": "NVDA", "name": "NVIDIA", "cik": "0001045810"}
        settings = {"embedding": {"model": "test-model"}, "vector_store": {"path": "test"}}
        collection = Mock()
        matches = [{"chunk_id": "report:1", "metadata": {"source_url": "https://example.com/report"}}]
        with patch("src.tools.report_search.resolve_company", return_value=company), patch(
            "src.tools.report_search.load_yaml", return_value=settings
        ), patch(
            "src.tools.report_search.get_vector_collection", return_value=collection
        ), patch("src.tools.report_search.search_reports", return_value=matches) as search:
            result = search_company_reports(" nvda ", "Risks?", fiscal_year=2026, top_k=3, section="Item 1A")

        search.assert_called_once_with(
            query="Risks?", collection=collection, embedding_config=settings["embedding"],
            top_k=3, ticker="NVDA", fiscal_year=2026, section="Item 1A",
        )
        
        self.assertEqual(result, {
            "company": company, "query": "Risks?", "fiscal_year": 2026,
            "section": "Item 1A", "matches": matches,
        })


if __name__ == "__main__":
    unittest.main()
