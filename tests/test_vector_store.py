import unittest
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from src.rag.vector_store import get_vector_collection, save_embedding_records


def make_record(chunk_id, cik="0000320193", accession="report-a", text="Report text"):
    return {
        "chunk_id": chunk_id,
        "text": text,
        "metadata": {"cik": cik, "accession_number": accession},
        "embedding": [1.0, 0.0, 0.0],
    }


class FilingRecordValidationTests(unittest.TestCase):
    def test_invalid_records_are_rejected_before_database_access(self):
        record = make_record("a:0")
        invalid_inputs = [
            None, [], {}, [None],
            [{**record, "chunk_id": ""}],
            [{**record, "text": "  "}],
            [{**record, "metadata": None}],
            [{**record, "metadata": {"cik": "0000320193"}}],
            [{**record, "metadata": {"cik": "", "accession_number": "report-a"}}],
            [{**record, "embedding": [float("nan"), 0.0, 0.0]}],
            [record, record],
            [record, make_record("b:0", accession="report-b")],
            [record, make_record("other:0", cik="0000789019")],
        ]

        for records in invalid_inputs:
            collection = Mock()

            with self.subTest(records=records), self.assertRaises(ValueError):
                save_embedding_records(collection, records)
            self.assertEqual(collection.mock_calls, [])


class FilingSynchronizationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="finsight-sync-test-")
        self.addCleanup(self.directory.cleanup)
        self.config = {"path": self.directory.name, "collection_name": "filing_sync_test"}
        self.collection = get_vector_collection(self.config)
        self.records = [make_record("a:0"), make_record("a:1")]
        save_embedding_records(self.collection, self.records)

    def test_shrinking_report_removes_stale_chunk_and_updates_retained_text(self):
        updated = make_record("a:0", text="Updated report text")
        self.assertEqual(save_embedding_records(self.collection, [updated]), 1)
        result = self.collection.get(include=["documents", "metadatas", "embeddings"])
        self.assertEqual(result["ids"], ["a:0"])
        self.assertEqual(result["documents"], [updated["text"]])
        self.assertEqual(result["metadatas"], [updated["metadata"]])
        self.assertEqual(result["embeddings"][0].tolist(), updated["embedding"])

    def test_other_accessions_and_other_companies_are_preserved(self):
        other_period = make_record("b:0", accession="report-b")
        other_company = make_record("other:0", cik="0000789019")
        save_embedding_records(self.collection, [other_period])
        save_embedding_records(self.collection, [other_company])
        save_embedding_records(self.collection, self.records[:1])
        self.assertEqual(set(self.collection.get(include=[])["ids"]), {"a:0", "b:0", "other:0"})

        for record in (other_period, other_company):
            result = self.collection.get(ids=[record["chunk_id"]])
            self.assertEqual(result["documents"], [record["text"]])
            self.assertEqual(result["metadatas"], [record["metadata"]])

    def test_completely_new_chunk_ids_replace_old_report(self):
        new_records = [make_record("new:0"), make_record("new:1")]
        save_embedding_records(self.collection, new_records)
        self.assertEqual(set(self.collection.get(include=[])["ids"]), {"new:0", "new:1"})

    def test_failed_upsert_does_not_delete_existing_chunks(self):
        with patch.object(type(self.collection), "upsert", side_effect=RuntimeError("Write failed")), patch.object(
            type(self.collection), "delete"
        ) as delete:
            with self.assertRaisesRegex(RuntimeError, "Write failed"):
                save_embedding_records(self.collection, self.records[:1])
            delete.assert_not_called()
        self.assertEqual(set(self.collection.get(include=[])["ids"]), {"a:0", "a:1"})

    def test_failed_delete_is_reported_and_retry_completes_sync(self):
        updated = make_record("a:0", text="Updated before deletion")

        with patch.object(type(self.collection), "delete", side_effect=RuntimeError("Delete failed")):
            with self.assertRaisesRegex(RuntimeError, "Delete failed"):
                save_embedding_records(self.collection, [updated])

        self.assertEqual(self.collection.get(ids=["a:0"])["documents"], [updated["text"]])
        self.assertEqual(self.collection.count(), 2)
        self.assertEqual(save_embedding_records(self.collection, [updated]), 1)
        self.assertEqual(self.collection.get(include=[])["ids"], ["a:0"])

    def test_read_failure_stops_before_writes_and_deletions(self):
        with patch.object(type(self.collection), "get", side_effect=RuntimeError("Read failed")), patch.object(
            type(self.collection), "upsert"
        ) as upsert, patch.object(type(self.collection), "delete") as delete:

            with self.assertRaisesRegex(RuntimeError, "Read failed"):
                save_embedding_records(self.collection, self.records[:1])

            upsert.assert_not_called()
            delete.assert_not_called()

    def test_repeated_sync_preserves_records_and_needs_no_deletion(self):
        save_embedding_records(self.collection, self.records[:1])

        with patch.object(type(self.collection), "delete") as delete:
            self.assertEqual(save_embedding_records(self.collection, self.records[:1]), 1)
            delete.assert_not_called()

        reopened = get_vector_collection(self.config)
        self.assertEqual(reopened.get(include=[])["ids"], ["a:0"])

    def test_chunk_id_owned_by_another_report_cannot_be_overwritten(self):
        foreign = make_record("reserved:0", accession="report-b", text="Other report")
        save_embedding_records(self.collection, [foreign])
        incoming = make_record("reserved:0", text="Wrong owner")

        with self.assertRaisesRegex(ValueError, "already belongs to another report"):
            save_embedding_records(self.collection, [incoming])
            
        result = self.collection.get(ids=["reserved:0"])
        self.assertEqual(result["documents"], [foreign["text"]])
        self.assertEqual(result["metadatas"], [foreign["metadata"]])
        self.assertEqual(set(self.collection.get(include=[])["ids"]), {"a:0", "a:1", "reserved:0"})


if __name__ == "__main__":
    unittest.main()
