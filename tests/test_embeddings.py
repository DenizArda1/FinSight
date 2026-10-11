import unittest
from unittest.mock import patch

from src.finsight.rag.embeddings import (
    embed_text,
    embed_texts,
    embed_texts_in_batches,
    validate_vectors,
)


class VectorValidationTests(unittest.TestCase):
    def test_valid_vectors_return_their_dimension_without_modification(self):
        vectors = [[0, 0.5, -1.0], [1.0, -0.5, 0]]
        self.assertEqual(validate_vectors(vectors, 2), 3)
        self.assertEqual(validate_vectors(vectors, 2, expected_dimension=3), 3)
        self.assertEqual(vectors, [[0, 0.5, -1.0], [1.0, -0.5, 0]])

    def test_missing_empty_or_invalid_vector_containers_are_rejected(self):
        for vectors in (None, {}, "invalid", [], [[]], [None], [(0.1, 0.2)]):
            with self.subTest(vectors=vectors), self.assertRaises(ValueError):
                validate_vectors(vectors, 1)

    def test_values_must_be_finite_numbers_and_not_booleans(self):
        invalid_values = [
            True, False, None, "0.5", [], {},
            float("nan"), float("inf"), -float("inf"), 10 ** 400,
        ]
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_vectors([[0.1, value]], 1)

    def test_mismatched_vector_counts_are_rejected(self):
        for vectors in ([], [[0.1], [0.2]]):
            with self.subTest(vectors=vectors), self.assertRaisesRegex(ValueError, "number of vectors"):
                validate_vectors(vectors, 1)

    def test_dimensions_must_match_within_response_and_expected_dimension(self):
        with self.assertRaisesRegex(ValueError, "dimension 1; expected 2"):
            validate_vectors([[0.1, 0.2], [0.3]], 2)
        with self.assertRaisesRegex(ValueError, "dimension 2; expected 1024"):
            validate_vectors([[0.1, 0.2]], 1, expected_dimension=1024)

    def test_invalid_expectations_are_rejected(self):
        for value in (0, -1, True, 1.5, "2"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "count must be a positive integer"):
                    validate_vectors([[0.1]], value)
                with self.assertRaisesRegex(ValueError, "dimension must be a positive integer"):
                    validate_vectors([[0.1]], 1, expected_dimension=value)


class EmbeddingClientTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "base_url": "http://localhost:11434",
            "model": "bge-m3:latest",
            "timeout_seconds": 120,
            "batch_size": 2,
        }
        patcher = patch("src.finsight.rag.embeddings.requests.post")
        self.post = patcher.start()
        self.addCleanup(patcher.stop)

    def test_invalid_api_vectors_are_rejected_by_single_text_entry_point(self):
        for vectors in ([[]], [None], [[1.0, float("nan")]], [[True]], [[float("inf")]]):
            self.post.return_value.json.return_value = {"embeddings": vectors}
            with self.subTest(vectors=vectors), self.assertRaises(ValueError):
                embed_text("Annual report", self.config)

    def test_non_object_response_and_missing_embeddings_are_rejected(self):
        for payload in (None, [], "invalid", {}):
            self.post.return_value.json.return_value = payload
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                embed_texts(["Annual report"], self.config)

    def test_api_response_with_inconsistent_dimensions_is_rejected(self):
        self.post.return_value.json.return_value = {"embeddings": [[0.1, 0.2], [0.3]]}
        with self.assertRaisesRegex(ValueError, "dimension 1; expected 2"):
            embed_texts(["First", "Second"], self.config)

    def test_batch_dimension_change_stops_before_remaining_requests(self):
        self.post.return_value.json.side_effect = [
            {"embeddings": [[0.1, 0.2], [0.3, 0.4]]},
            {"embeddings": [[0.5, 0.6, 0.7], [0.8, 0.9, 1.0]]},
        ]
        with self.assertRaisesRegex(ValueError, "dimension 3; expected 2"):
            embed_texts_in_batches(["First", "Second", "Third", "Fourth", "Fifth"], self.config)
        self.assertEqual(self.post.call_count, 2)

    def test_final_short_batch_preserves_all_vectors_in_order(self):
        vectors = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        self.post.return_value.json.side_effect = [
            {"embeddings": vectors[:2]}, {"embeddings": vectors[2:]},
        ]
        result = embed_texts_in_batches(["First", "Second", "Third"], self.config)
        self.assertEqual(result, vectors)
        batches = [call.kwargs["json"]["input"] for call in self.post.call_args_list]
        self.assertEqual(batches, [["First", "Second"], ["Third"]])


if __name__ == "__main__":
    unittest.main()
