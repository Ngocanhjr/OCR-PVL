"""Compatibility wrapper for the OCR Markdown postprocess pipeline.

The implementation now lives under `processing.postprocess` so individual rules
can stay small and testable. Keep this module as the stable import path for
existing callers.
"""

from __future__ import annotations

from processing.postprocess.pipeline import (
    DEFAULT_POSTPROCESS_RULES,
    PostprocessRule,
    postprocess_final_markdown,
    run_postprocess_pipeline,
)
from processing.postprocess.rules.forms import normalize_form_layout
from processing.postprocess.rules.headings import normalize_ctu_markdown_headings
from processing.postprocess.rules.scanner import remove_scanner_watermarks
from processing.postprocess.rules.tables import (
    extract_last_table_header,
    is_table_row,
    is_table_separator,
    line_to_continued_table_row,
    make_separator,
    make_table_row,
    normalize_table_cell_breaks,
    normalize_table_column_counts,
    page_has_table_header,
    repair_continued_tables_across_pages,
    repair_data_row_used_as_header,
    repair_shifted_disciplinary_table_rows,
    split_table_row,
    starts_with_table_continuation,
)
from processing.postprocess.rules.text_artifacts import (
    normalize_llamaparse_rag_artifacts,
    normalize_toc_dot_leaders,
)

__all__ = [
    "DEFAULT_POSTPROCESS_RULES",
    "PostprocessRule",
    "extract_last_table_header",
    "is_table_row",
    "is_table_separator",
    "line_to_continued_table_row",
    "make_separator",
    "make_table_row",
    "normalize_ctu_markdown_headings",
    "normalize_form_layout",
    "normalize_llamaparse_rag_artifacts",
    "normalize_table_cell_breaks",
    "normalize_table_column_counts",
    "normalize_toc_dot_leaders",
    "page_has_table_header",
    "postprocess_final_markdown",
    "remove_scanner_watermarks",
    "repair_continued_tables_across_pages",
    "repair_data_row_used_as_header",
    "repair_shifted_disciplinary_table_rows",
    "run_postprocess_pipeline",
    "split_table_row",
    "starts_with_table_continuation",
]
