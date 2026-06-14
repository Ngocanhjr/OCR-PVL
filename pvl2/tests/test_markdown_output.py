from __future__ import annotations

import unittest

from processing.page_markers import (
    clean_page_block,
    page_marker,
    split_markdown_by_page,
)
from processing.table_form_postprocess import postprocess_final_markdown


class MarkdownOutputContractTest(unittest.TestCase):
    def test_page_marker_is_html_comment_not_heading(self) -> None:
        marker = page_marker(1)

        self.assertEqual(marker, "<!-- page: 1 -->")
        self.assertFalse(marker.startswith("#"))

    def test_clean_page_block_preserves_marker_and_removes_trailing_separator(self) -> None:
        cleaned = clean_page_block("<!-- page: 3 -->\n\nNội dung\n\n---\n")

        self.assertTrue(cleaned.startswith("<!-- page: 3 -->"))
        self.assertIn("Nội dung", cleaned)
        self.assertFalse(cleaned.rstrip().endswith("---"))

    def test_split_markdown_by_page_preserves_page_order(self) -> None:
        markdown = "<!-- page: 1 -->\nA\n\n<!-- page: 2 -->\nB"

        blocks = split_markdown_by_page(markdown)

        self.assertEqual(list(blocks), [1, 2])
        self.assertIn("A", blocks[1])
        self.assertIn("B", blocks[2])

    def test_final_postprocess_keeps_page_comments_and_table(self) -> None:
        markdown = (
            "<!-- page: 1 -->\n\n"
            "| Cột A | Cột B |\n"
            "| --- | --- |\n"
            "| 1 | Nội dung |\n\n"
            "<!-- page: 2 -->\n\n"
            "Nội dung trang 2"
        )

        output = postprocess_final_markdown(markdown)

        self.assertIn("<!-- page: 1 -->", output)
        self.assertIn("<!-- page: 2 -->", output)
        self.assertIn("| Cột A | Cột B |", output)
        self.assertIn("| 1 | Nội dung |", output)

    def test_final_postprocess_converts_dash_breaks_inside_table_cells(self) -> None:
        dash_break = "-" * 4
        markdown = (
            "<!-- page: 1 -->\n\n"
            "| Cột A | Cột B |\n"
            "| --- | --- |\n"
            f"| Dòng 1 {dash_break} Dòng 2 | Giữ nguyên |\n"
        )

        output = postprocess_final_markdown(markdown)

        self.assertIn("| --- | --- |", output)
        self.assertIn("| Dòng 1<br>Dòng 2 | Giữ nguyên |", output)
        self.assertNotIn(dash_break, output)


if __name__ == "__main__":
    unittest.main()
