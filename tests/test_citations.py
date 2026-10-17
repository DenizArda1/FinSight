import unittest

from src.verification.citations import validate_citations


class CitationTests(unittest.TestCase):
    def test_first_middle_and_last_sources_are_valid(self):
        matches = [{}, {}, {}]
        for answer in ("Risk [Source 1].", "Risk [Source 2].", "Risk [Source 3]."):
            with self.subTest(answer=answer):
                self.assertTrue(validate_citations(answer, matches))

    def test_single_source_is_valid(self):
        self.assertTrue(validate_citations("Risk [Source 1].", [{}]))

    def test_repeated_and_out_of_order_citations_are_valid(self):
        self.assertTrue(validate_citations(
            "Risk [Source 3]. Detail [Source 1]. More detail [Source 3].",
            [{}, {}, {}],
        ))

    def test_missing_citations_raise_instead_of_returning_an_exception(self):
        for answer in ("", "No citation in this answer."):
            with self.subTest(answer=answer), self.assertRaisesRegex(ValueError, "must include source citations"):
                validate_citations(answer, [{}])

    def test_zero_and_out_of_range_citations_are_rejected(self):
        for number in (0, 4, 12):
            answer = f"Valid claim [Source 1]. Invalid claim [Source {number}]."
            with self.subTest(number=number), self.assertRaisesRegex(ValueError, "outside the available source range"):
                validate_citations(answer, [{}, {}, {}])

    def test_citation_without_any_available_sources_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the available source range"):
            validate_citations("Risk [Source 1].", [])

    def test_valid_citation_does_not_hide_a_malformed_one(self):
        for citation in ("[Source -1]", "[Source1]", "[Source x]", "[source 1]", "[Source 2"):
            with self.subTest(citation=citation), self.assertRaisesRegex(ValueError, "Malformed"):
                validate_citations(f"Claim [Source 1]. Other claim {citation}", [{}])

    def test_source_free_clarification_can_skip_required_citations(self):
        self.assertTrue(validate_citations("Which company?", [], require_citations=False))
        with self.assertRaises(ValueError):
            validate_citations("Which company? [Source 1]", [], require_citations=False)


if __name__ == "__main__":
    unittest.main()
