import unittest
from src.finsight.rag.chunking import build_document_chunks, split_text


class ChunkingTests(unittest.TestCase):
    def test_chunks_preserve_source_positions_and_overlap(self):
        text = "abcdefghijklmnopqrstuvwxyz"

        chunks = split_text(text, max_chars=10, overlap=2)

        self.assertEqual([chunk["start"] for chunk in chunks], [0, 8, 16])
        self.assertEqual(chunks[-1]["end"], len(text))
        for chunk in chunks:
            self.assertEqual(chunk["text"], text[chunk["start"]:chunk["end"]])
            self.assertLessEqual(len(chunk["text"]), 10)

    def test_paragraph_boundary_is_used_when_possible(self):
        text = "First paragraph.\n\nSecond paragraph."

        chunks = split_text(text, max_chars=20, overlap=0)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["text"], "First paragraph.")
        self.assertEqual(chunks[1]["text"], "Second paragraph.")
        for chunk in chunks:
            self.assertEqual(chunk["text"], text[chunk["start"]:chunk["end"]])

    def test_empty_text_produces_no_chunks(self):
        self.assertEqual(split_text(""), [])
        self.assertEqual(split_text(" \n\t "), [])

    def test_non_string_text_is_rejected(self):
        for text in [None, 123, []]:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "Text must be a string"):
                    split_text(text)

    def test_invalid_max_chars_is_rejected(self):
        for max_chars in [0, -1, True, 1.5, "1500"]:
            with self.subTest(max_chars=max_chars):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    split_text("Annual report", max_chars=max_chars)

    def test_invalid_overlap_is_rejected(self):
        for overlap in [-1, 10, 11, True, 1.5, "2"]:
            with self.subTest(overlap=overlap):
                with self.assertRaisesRegex(ValueError, "Overlap must be an integer"):
                    split_text("Annual report", max_chars=10, overlap=overlap)

    def test_document_chunks_preserve_identity_metadata_and_source_positions(self):
        document = {
            "company": {"ticker": "AAPL", "cik": "0000320193"},
            "filing": {
                "accessionNumber": "test-accession",
                "reportDate": "2025-09-27",
                "url": "https://example.invalid/report",
            },
            "text": "Annual revenue increased.\n" * 200,
        }

        chunks = build_document_chunks(document)

        self.assertGreater(len(chunks), 1)
        self.assertEqual(len({chunk["chunk_id"] for chunk in chunks}), len(chunks))
        for index, chunk in enumerate(chunks):
            metadata = chunk["metadata"]
            self.assertEqual(chunk["chunk_id"], f"test-accession:{index}")
            self.assertEqual(metadata["ticker"], "AAPL")
            self.assertEqual(metadata["cik"], "0000320193")
            self.assertEqual(metadata["accession_number"], "test-accession")
            self.assertEqual(metadata["report_date"], "2025-09-27")
            self.assertEqual(metadata["source_url"], "https://example.invalid/report")
            self.assertEqual(chunk["text"], document["text"][metadata["start"]:metadata["end"]])


if __name__ == "__main__":
    unittest.main()
