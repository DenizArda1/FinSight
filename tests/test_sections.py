import unittest

from src.rag.sections import extract_sections, extract_cross_reference_chapters
from tests.filing_fixtures import REPORT_TEXT


class SectionTests(unittest.TestCase):
    def test_explicit_mda_reference_follows_separate_caption(self):
        prefix = REPORT_TEXT.split("Item 7.")[0]
        stub = ("Item 7. Management’s Discussion and Analysis\n"
                "See the information under the caption “Management’s Discussion and Analysis.”\n"
                "Item 7A. Quantitative and Qualitative Disclosures\nMarket risk reference.\n"
                "Item 8. Financial Statements\nSee statements.\nItem 16. Summary\nNone.\n")
        chapter = "MANAGEMENT’S DISCUSSION AND ANALYSIS\n" + 'Actual operating results. ' * 30
        boundary = "\nFINANCIAL INSTRUMENT MARKET RISK INFORMATION\nExcluded risk and financial statements."
        text = prefix + stub + chapter + boundary
        sections = extract_sections(text)
        mda = sections[2]
        self.assertEqual(mda['section'], 'Item 7')
        self.assertEqual(mda['text'], text[mda['start']:mda['end']])
        self.assertIn('Actual operating results.', mda['text'])
        self.assertNotIn('Excluded', mda['text'])
        self.assertLess(mda['reference_start'], mda['start'])
        for invalid in (text.replace('See the information under the caption', 'Unrelated text'),
                        text.replace(boundary, ''), text + '\n' + chapter + boundary):
            with self.subTest(text=invalid[-100:]), self.assertRaises(ValueError):
                extract_sections(invalid)

    def test_cross_reference_chapters_exclude_toc_and_repeated_page_footers(self):
        text = ("Form 10-K Cross-Reference Index\n"
                "\tManagement's Discussion and Analysis\t\nOverview\n"
                "Risk Factors\n37\nOther Key Information\n52\n"
                "Management's Discussion and Analysis\nOverview\n" + "Results improved. " * 30 +
                "\nRisk Factors\nOur material risks include competition. " + "Risk discussion. " * 30 +
                "\nRisk Factors\n38\n" + "More risks. " * 30 +
                "\nOther Key Information\nInformation About Executive Officers\nExcluded")
        sections = extract_cross_reference_chapters(text)
        self.assertEqual([entry['section'] for entry in sections], ['Item 7', 'Item 1A'])
        self.assertNotIn('Excluded', sections[-1]['text'])
        self.assertIn('More risks.', sections[-1]['text'])
        for entry in sections:
            self.assertEqual(entry['text'], text[entry['start']:entry['end']])
        with self.assertRaises(ValueError):
            extract_cross_reference_chapters(text.replace('Form 10-K Cross-Reference Index', 'Contents'))

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
