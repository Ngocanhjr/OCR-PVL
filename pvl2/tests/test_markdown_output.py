from __future__ import annotations

import unittest

from processing.page_markers import (
    clean_page_block,
    page_marker,
    split_markdown_by_page,
)
from processing.table_form_postprocess import postprocess_final_markdown
from engines.llamaparse_engine import tao_llama_config


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

    def test_final_postprocess_removes_break_artifacts_inside_table_cells(self) -> None:
        dash_break = "-" * 4
        markdown = (
            "<!-- page: 1 -->\n\n"
            "| Cột A | Cột B |\n"
            "| --- | --- |\n"
            f"| Dòng 1 {dash_break} Dòng 2<br/>Dòng 3 | Giữ nguyên |\n"
        )

        output = postprocess_final_markdown(markdown)

        self.assertIn("| --- | --- |", output)
        self.assertIn("| Dòng 1; Dòng 2; Dòng 3 | Giữ nguyên |", output)
        self.assertNotIn(dash_break, output)
        self.assertNotIn("<br", output.lower())

    def test_final_postprocess_repairs_shifted_disciplinary_table_row(self) -> None:
        markdown = (
            "<!-- page: 1 -->\n\n"
            "| TT | Nội dung vi phạm | Lần 1 | Lần 2 | Lần 3 | Ghi chú |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| 12 | Tiếp khách trong phòng ở. | Nhắc nhở | Khiển trách toàn KTX | Cảnh cáo toàn KTX | |\n"
            "| Tiếp người khác giới trong phòng ở. | Cảnh cáo toàn KTX | Buộc ra khỏi KTX | | | |\n"
        )

        output = postprocess_final_markdown(markdown)

        self.assertIn(
            "| | Tiếp người khác giới trong phòng ở. | Cảnh cáo toàn KTX | Buộc ra khỏi KTX | | |",
            output,
        )

    def test_llamaparse_config_keeps_continued_tables_on_original_pages(self) -> None:
        cfg = tao_llama_config(page_start=4, page_end=6)

        self.assertFalse(cfg.merge_continued_tables)


if __name__ == "__main__":
    unittest.main()
