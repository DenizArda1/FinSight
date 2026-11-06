import unittest
from copy import deepcopy
from uuid import uuid4
from unittest.mock import Mock, patch

import chromadb

from src.rag.retrieval import format_search_results, get_latest_report_metadata, search_reports
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
            ({"ticker": "AAPL", "section": "Item 1A", "accession_number": "report-id"},
             {"$and": [{"ticker": "AAPL"}, {"section": "Item 1A"}, {"accession_number": "report-id"}]}),
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
            {"accession_number": " "}, {"accession_number": True},
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
        ), patch("src.tools.report_search.search_reports", return_value=matches) as search, patch(
            "src.tools.report_search.expand_search_matches", return_value=matches
        ) as expand:
            result = search_company_reports(" nvda ", "Risks?", fiscal_year=2026, top_k=3, section="Item 1A")

        search.assert_called_once_with(
            query="Risks?", collection=collection, embedding_config=settings["embedding"],
            top_k=3, ticker="NVDA", fiscal_year=2026, section="Item 1A", accession_number=None, report_date=None, hybrid=True,
        )
        self.assertEqual(expand.call_args.args[0], matches)
        
        self.assertEqual(result, {
            "company": company, "query": "Risks?", "fiscal_year": 2026,
            "section": "Item 1A", "matches": matches,
        })


class LatestReportTests(unittest.TestCase):
    def setUp(self):
        self.old = {
            "ticker": "AAPL", "fiscal_year": 2023, "report_date": "2023-09-30",
            "accession_number": "0000320193-23-000106", "section": "Item 1A",
        }
        self.new = {
            "ticker": "AAPL", "cik": "0000320193", "fiscal_year": 2025, "report_date": "2025-09-27",
            "accession_number": "0000320193-25-000079", "section": "Item 1A",
        }
        self.collection = Mock()
        self.collection.get.return_value = {"metadatas": [self.new, self.old, deepcopy(self.new)]}

    def test_selects_latest_period_and_deduplicates_chunks(self):
        result = get_latest_report_metadata(self.collection, " aapl ")
        self.assertEqual(result, {key: self.new[key] for key in ("fiscal_year", "report_date", "accession_number")})
        self.collection.get.assert_called_once_with(where={"ticker": "AAPL"}, include=["metadatas"])
        self.collection.query.assert_not_called()

    def test_does_not_infer_fiscal_year_from_calendar_date(self):
        self.new["ticker"] = self.old["ticker"] = "NVDA"
        self.new["report_date"] = "2025-12-28"
        self.new["fiscal_year"] = 2026
        self.collection.get.return_value = {"metadatas": [self.new, self.old]}
        result = get_latest_report_metadata(self.collection, "NVDA")
        self.assertEqual(result["fiscal_year"], 2026)

    def test_invalid_ticker_is_rejected_before_reading_collection(self):
        for ticker in (None, 123, [], "", " \t"):
            with self.subTest(ticker=ticker), self.assertRaises(ValueError):
                get_latest_report_metadata(self.collection, ticker)
        self.collection.get.assert_not_called()

    def test_empty_or_missing_metadata_is_rejected(self):
        for metadata in ([], None, {}):
            self.collection.get.return_value = {"metadatas": metadata}
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                get_latest_report_metadata(self.collection, "AAPL")

    def test_invalid_index_metadata_is_rejected_instead_of_ignoring_it(self):
        changes = [
            {"report_date": "2025-02-30"}, {"report_date": "20250927"},
            {"report_date": None}, {"fiscal_year": True}, {"fiscal_year": "2025"},
            {"fiscal_year": 0}, {"accession_number": "bad"}, {"ticker": "MSFT"},
        ]
        for change in changes:
            self.collection.get.return_value = {"metadatas": [self.new, {**self.old, **change}]}
            with self.subTest(change=change), self.assertRaises(ValueError):
                get_latest_report_metadata(self.collection, "AAPL")

    def test_conflicting_chunks_and_ambiguous_latest_reports_are_rejected(self):
        for changed in ({**self.new, "fiscal_year": 2024},
                        {**self.new, "accession_number": "0000320193-25-000080"}):
            self.collection.get.return_value = {"metadatas": [self.new, changed]}
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                get_latest_report_metadata(self.collection, "AAPL")


class LatestReportSearchTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("src.rag.index_identity.verify_collection_identity", return_value={"embedding_digest": "test"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.company = {"ticker": "AAPL", "cik": "0000320193", "name": "Apple Inc."}
        company_patcher = patch("src.tools.report_search.resolve_company", return_value=self.company)
        self.resolve = company_patcher.start()
        self.addCleanup(company_patcher.stop)
        settings_patcher = patch("src.tools.report_search.load_yaml", return_value={"embedding": {}, "vector_store": {}})
        settings_patcher.start()
        self.addCleanup(settings_patcher.stop)
        collection_patcher = patch("src.tools.report_search.get_vector_collection")
        self.get_collection = collection_patcher.start()
        self.addCleanup(collection_patcher.stop)
        self.latest = {
            "ticker": "AAPL", "cik": "0000320193", "fiscal_year": 2025, "report_date": "2025-09-27",
            "accession_number": "0000320193-25-000079", "section": "Item 1A",
        }

    def test_invalid_latest_options_are_rejected_before_data_access(self):
        for kwargs in ({"latest": "true"}, {"latest": 1}, {"latest": None},
                       {"latest": True, "fiscal_year": 2023}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                search_company_reports("AAPL", "Risks?", **kwargs)
        self.resolve.assert_not_called()

    @patch("src.rag.retrieval.embed_text", return_value=[1.0, 0.0])
    @patch("src.tools.report_search.expand_search_matches")
    def test_real_collection_filters_to_latest_accession_without_older_section_fallback(self, expand, embed):
        # This test isolates Chroma filtering; prepared-report expansion is tested separately.
        expand.side_effect = lambda matches, processed_path: matches
        client = chromadb.EphemeralClient()
        name = f"latest-test-{uuid4().hex}"
        collection = client.create_collection(name=name, embedding_function=None)
        self.addCleanup(client.delete_collection, name)
        old = {**self.latest, "fiscal_year": 2023, "report_date": "2023-09-30",
               "accession_number": "0000320193-23-000106"}
        collection.add(
            ids=["old-risk", "new-risk", "old-business"],
            documents=["Old risk evidence", "New risk evidence", "Old business evidence"],
            metadatas=[old, self.latest, {**old, "section": "Item 1"}],
            embeddings=[[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]],
        )
        self.get_collection.return_value = collection
        result = search_company_reports("AAPL", "Risks?", section="Item 1A", latest=True, top_k=1)
        self.assertEqual(result["matches"][0]["chunk_id"], "new-risk")
        self.assertEqual(result["fiscal_year"], 2025)
        self.assertEqual(result["selected_report"]["accession_number"], self.latest["accession_number"])
        self.assertTrue(result["latest"])
        missing_section = search_company_reports("AAPL", "Business?", section="Item 1", latest=True)
        self.assertEqual(missing_section["matches"], [])
        self.assertEqual(missing_section["selected_report"], result["selected_report"])
        historical = search_company_reports("AAPL", "Risks?", fiscal_year=2023, section="Item 1A")
        self.assertEqual(historical["matches"][0]["chunk_id"], "old-risk")
        all_years = search_company_reports("AAPL", "Risks?", section="Item 1A", top_k=1)
        self.assertEqual(all_years["matches"][0]["chunk_id"], "old-risk")

    @patch("src.rag.retrieval.embed_text")
    def test_no_indexed_reports_fails_before_embedding(self, embed):
        self.get_collection.return_value.get.return_value = {"metadatas": []}
        with self.assertRaisesRegex(ValueError, "No indexed reports"):
            search_company_reports("AAPL", "Risks?", latest=True)
        embed.assert_not_called()
        self.get_collection.return_value.query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
