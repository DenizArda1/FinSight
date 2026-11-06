import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from src.rag.hybrid import bm25_rank, reciprocal_rank_fusion
from src.rag.versions import active_records
from src.rag.index_identity import verify_collection_identity
from src.rag.sections import extract_sections
from src.tools.financial_metrics import compare_companies
from src.verification.agent_answer import build_agent_evidence, build_fact_catalog, render_agent_template, compose_template


class HybridTests(unittest.TestCase):
    def test_rare_exact_terms_are_retrieved_and_fused_without_duplicates(self):
        records = [{"chunk_id": "a", "text": "cloud cloud revenue"},
                   {"chunk_id": "b", "text": "Mellanox acquisition approval"}]
        lexical = bm25_rank("Mellanox", records, 5)
        self.assertEqual([row["chunk_id"] for row in lexical], ["b"])
        fused = reciprocal_rank_fusion([records[0], records[1]], lexical, 5)
        self.assertEqual([row["chunk_id"] for row in fused], ["b", "a"])
        self.assertEqual(fused[0]["ranks"], {"dense": 2, "bm25": 1})

    def test_amendment_replaces_only_its_section_and_same_period(self):
        base = {"cik": "1", "report_date": "2025-12-31", "section": "Item 7", "filed": "2026-02-01", "accession_number": "original"}
        records = [
            {"chunk_id": "old-mdna", "metadata": base},
            {"chunk_id": "risk", "metadata": {**base, "section": "Item 1A"}},
            {"chunk_id": "amended-mdna", "metadata": {**base, "filed": "2026-03-01", "accession_number": "amended"}},
            {"chunk_id": "prior", "metadata": {**base, "report_date": "2024-12-31"}},
        ]
        self.assertEqual([row["chunk_id"] for row in active_records(records)], ["risk", "amended-mdna", "prior"])

    def test_partial_amendment_and_non_narrative_amendment(self):
        text = "Item 7. Management's Discussion and Analysis\n" + "Replacement discussion. " * 30 + "\nItem 8. Financial Statements\nOther text"
        sections = extract_sections(text, partial=True)
        self.assertEqual([section["section"] for section in sections], ["Item 7"])
        self.assertNotIn("Financial Statements", sections[0]["text"])
        self.assertEqual(extract_sections("Item 12. Ownership\n" + "Other text " * 50, partial=True), [])

    @patch("src.rag.index_identity.embedding_identity", return_value={"embedding_model": "bge", "embedding_digest": "abc", "index_schema": 1})
    def test_identity_cannot_be_added_to_populated_legacy_index(self, identity):
        collection = Mock(metadata=None)
        collection.count.return_value = 5
        with self.assertRaisesRegex(ValueError, "Rebuild"):
            verify_collection_identity(collection, {}, initialize=True)
        collection.modify.assert_not_called()
        collection.count.return_value = 0
        verify_collection_identity(collection, {}, initialize=True)
        collection.modify.assert_called_once()
        collection.metadata = {"embedding_model": "bge", "embedding_digest": "different", "index_schema": 1}
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify_collection_identity(collection, {})


class ComparisonTests(unittest.TestCase):
    @patch("src.tools.financial_metrics.get_company_facts")
    @patch("src.tools.financial_metrics.resolve_company")
    def test_comparison_keeps_dates_units_and_renderable_source_paths(self, resolve, facts):
        resolve.side_effect = [{"ticker": "A", "cik": "0000000001"}, {"ticker": "B", "cik": "0000000002"}]
        row = {"metric": "revenue", "value": 100, "unit": "USD", "start": "2024-10-01", "end": "2025-09-30", "fiscal_year": 2025, "form": "10-K", "accn": "source", "tag": "Revenues"}
        facts.side_effect = [{"records": [row], "missing_period_ends": []},
                             {"records": [{**row, "end": "2025-12-31", "value": 200}], "missing_period_ends": []}]
        result = compare_companies(["A", "B"], ["revenue"], 1)
        self.assertEqual([record["end"] for record in result["records"]], ["2025-09-30", "2025-12-31"])
        evidence = build_agent_evidence([{"type": "tool", "status": "completed", "name": "compare_companies", "arguments": {}, "result": result}])
        catalog = build_fact_catalog(evidence)
        answer = render_agent_template(compose_template({"kind": "answer", "text": "", "facts": list(catalog)}, catalog), evidence)
        self.assertIn("200 USD", answer)
        self.assertIn("2025-12-31", answer)

    @patch("src.tools.financial_metrics.get_company_facts")
    @patch("src.tools.financial_metrics.resolve_company")
    def test_missing_company_values_are_not_zero_filled(self, resolve, facts):
        resolve.side_effect = [{"ticker": "A", "cik": "0000000001"}, {"ticker": "B", "cik": "0000000002"}]
        facts.return_value = {"records": [], "missing_period_ends": ["2025-12-31"]}
        result = compare_companies(["A", "B"], ["revenue"], 1)
        self.assertEqual(result["records"], [])
        self.assertTrue(result["warnings"])
