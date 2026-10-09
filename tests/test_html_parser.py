import unittest

from src.finsight.rag.html_parser import extract_text, normalize_text


class HtmlParserTests(unittest.TestCase):
    def test_hidden_elements_are_removed_and_visible_values_are_kept(self):
        html = """
        <html><head><title>HEAD_TEXT</title><style>STYLE_TEXT</style></head>
        <body>
            <script>SCRIPT_TEXT</script>
            <ix:header><ix:hidden>XBRL_METADATA</ix:hidden></ix:header>
            <div hidden><span>HIDDEN_ATTRIBUTE</span></div>
            <div hidden="false">HIDDEN_FALSE_ATTRIBUTE</div>
            <div style="DISPLAY : none !important"><p>HIDDEN_STYLE</p></div>
            <p>Revenue <ix:nonfraction>100</ix:nonfraction> dollars.</p>
        </body></html>
        """

        self.assertEqual(extract_text(html), "Revenue 100 dollars.")

    def test_inline_display_declarations_respect_order_and_important(self):
        cases = [
            ("display: none; display: block", "VISIBLE"),
            ("display: block; display: none", ""),
            ("display: none !important; display: block", ""),
            ("display: none !important; display: block !important", "VISIBLE"),
            ("display: /* comment */ none", ""),
        ]
        for style, expected in cases:
            with self.subTest(style=style):
                self.assertEqual(extract_text(f'<div style="{style}">VISIBLE</div>'), expected)

    def test_inline_tags_do_not_split_a_sentence(self):
        html = "<p>Revenue increased <span>10%</span> this year.</p>"

        self.assertEqual(extract_text(html), "Revenue increased 10% this year.")

    def test_table_rows_and_cells_remain_separated(self):
        html = "<table><tr><th>Year</th><th>Revenue</th></tr><tr><td>2025</td><td>100</td></tr></table>"

        self.assertEqual(extract_text(html), "\tYear\tRevenue\n\t2025\t100")

    def test_normalization_keeps_cell_separators(self):
        text = "  Annual\xa0  report  \n\n\t2025\t100\n \t \n"

        self.assertEqual(normalize_text(text), "Annual report\n\t2025\t100")

    def test_html_without_visible_text_produces_empty_text(self):
        html = "<head><title>Title</title></head><script>code()</script><div hidden>Hidden</div>"

        self.assertEqual(extract_text(html), "")

    def test_invalid_html_is_rejected(self):
        for html in (None, 123, "", "   "):
            with self.subTest(html=html):
                with self.assertRaisesRegex(ValueError, "HTML must be a non-empty string"):
                    extract_text(html)


if __name__ == "__main__":
    unittest.main()
