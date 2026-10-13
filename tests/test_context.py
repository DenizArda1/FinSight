from copy import deepcopy
import unittest

from src.finsight.rag.context import build_report_context


class ReportContextTests(unittest.TestCase):
    def test_empty_matches_produce_empty_context(self):
        self.assertEqual(build_report_context([]), "")

    def test_source_numbers_remain_paired_with_their_metadata_and_text(self):
        matches = [
            {
                "chunk_id": "report-a:2", "distance": 0.2,
                "metadata": {
                    "ticker": "NVDA", "fiscal_year": 2026, "section": "Item 1A",
                    "source_url": "https://example.com/nvda-2026", "accession_number": "report-a",
                },
                "text": "Export restrictions.\nİhracat riskleri: $100 & <limits>.",
            },
            {
                "chunk_id": "report-b:1", "distance": 0.4,
                "metadata": {
                    "ticker": "AAPL", "fiscal_year": 2025, "section": "Item 7",
                    "source_url": "https://example.com/aapl-2025", "accession_number": "report-b",
                },
                "text": "Operating results.",
            },
        ]
        original = deepcopy(matches)
        context = build_report_context(matches)

        self.assertEqual(context, 
        (
            "[Source 1]\n"
            "Company: NVDA\n"
            "Fiscal year: 2026\n"
            "Section: Item 1A\n"
            "URL: https://example.com/nvda-2026\n"
            "Text: Export restrictions.\nİhracat riskleri: $100 & <limits>.\n\n"
            "[Source 2]\n"
            "Company: AAPL\n"
            "Fiscal year: 2025\n"
            "Section: Item 7\n"
            "URL: https://example.com/aapl-2025\n"
            "Text: Operating results."
        ))
        self.assertEqual(matches, original)


if __name__ == "__main__":
    unittest.main()
