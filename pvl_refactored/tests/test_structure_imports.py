from __future__ import annotations

import unittest


class StructureImportTest(unittest.TestCase):
    def test_processing_modules_are_available_from_new_packages(self) -> None:
        from processing.page_markers import page_marker
        from processing.table_form_postprocess import postprocess_final_markdown

        self.assertEqual(page_marker(1), "<!-- page: 1 -->")
        self.assertIn("<!-- page: 1 -->", postprocess_final_markdown("## Trang 1\nNội dung"))

    def test_router_modules_are_available_from_new_packages(self) -> None:
        from pipeline.hybrid_page_router import parse_manual_pages
        from pipeline.hybrid_router import run_document_parse

        self.assertEqual(parse_manual_pages("1,3-4"), [1, 3, 4])
        self.assertTrue(callable(run_document_parse))


if __name__ == "__main__":
    unittest.main()
