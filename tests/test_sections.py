import unittest

from src.finsight.rag.sections import extract_sections
from tests.filing_fixtures import REPORT_TEXT


class SectionTests(unittest.TestCase):
    def test_toc_is_ignored_and_sections_match_source_spans(self):
        toc = (
            "Item 1.\nBusiness\n3\nItem 1A.\nRisk Factors\n5\n"
            "Item 1B. Unresolved Staff Comments\n8\n"
            "Item 7. Management's Discussion and Analysis\n20\n"
            "Item 7A. Quantitative and Qualitative Disclosures\n30\n"
        )
        text = toc + REPORT_TEXT
        sections = extract_sections(text)
        self.assertEqual([s["section"] for s in sections], ["Item 1", "Item 1A", "Item 7"])
        for section in sections:
            self.assertGreaterEqual(section["start"], len(toc))
            self.assertEqual(section["text"], text[section["start"]:section["end"]])
            self.assertNotIn("Excluded", section["text"])

    def test_bare_page_headers_are_not_section_boundaries(self):
        text = REPORT_TEXT.replace("Changes in demand", "Item 1A\nBusiness model competition\nChanges in demand", 1)
        sections = extract_sections(text)
        self.assertIn("Business model competition", sections[1]["text"])
        self.assertIn("can affect our business", sections[1]["text"])

    def test_wrapped_tabbed_and_uppercase_headings(self):
        text = REPORT_TEXT.upper().replace("ITEM 1. BUSINESS", "\tITEM 1.\t\nBUSINESS")
        text = text.replace("DISCUSSION AND ANALYSIS", "DISCUSSION\nAND ANALYSIS")
        self.assertEqual(len(extract_sections(text)), 3)

    def test_missing_or_ambiguous_sections_are_rejected(self):
        for text in (REPORT_TEXT.replace("Item 1A. Risk Factors", "Risks"), REPORT_TEXT + "\n" + REPORT_TEXT):
            with self.subTest(text=text[:40]):
                with self.assertRaisesRegex(ValueError, "Expected one substantive"):
                    extract_sections(text)

    def test_toc_only_and_missing_final_boundary_are_rejected(self):
        for text in ("Item 1. Business\n1\nItem 1A. Risk Factors\n2", REPORT_TEXT.split("Item 7A.")[0]):
            with self.subTest(text=text[:40]):
                with self.assertRaises(ValueError):
                    extract_sections(text)

    def test_item_8_can_end_mda_when_item_7a_is_absent(self):
        text = REPORT_TEXT.replace("Item 7A. Quantitative and Qualitative Disclosures About Market Risk\nExcluded market risk content.\n", "")
        sections = extract_sections(text)
        self.assertNotIn("Item 8", sections[2]["text"])


if __name__ == "__main__":
    unittest.main()
