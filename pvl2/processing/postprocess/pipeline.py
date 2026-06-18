from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

from config import lam_sach_text
from processing.postprocess.rules.forms import normalize_form_layout
from processing.postprocess.rules.headings import normalize_ctu_markdown_headings
from processing.postprocess.rules.scanner import remove_scanner_watermarks
from processing.postprocess.rules.tables import (
    normalize_table_column_counts,
    repair_continued_tables_across_pages,
    repair_data_row_used_as_header,
    repair_shifted_disciplinary_table_rows,
)
from processing.postprocess.rules.text_artifacts import (
    normalize_llamaparse_rag_artifacts,
    normalize_toc_dot_leaders,
)


@dataclass(frozen=True)
class PostprocessRule:
    name: str
    apply: Callable[[str], str]


DEFAULT_POSTPROCESS_RULES: tuple[PostprocessRule, ...] = (
    PostprocessRule("remove_scanner_watermarks", remove_scanner_watermarks),
    PostprocessRule("normalize_llamaparse_rag_artifacts", normalize_llamaparse_rag_artifacts),
    PostprocessRule("normalize_toc_dot_leaders", normalize_toc_dot_leaders),
    PostprocessRule("normalize_form_layout", normalize_form_layout),
    PostprocessRule("normalize_ctu_markdown_headings", normalize_ctu_markdown_headings),
    PostprocessRule("repair_data_row_used_as_header", repair_data_row_used_as_header),
    PostprocessRule("normalize_table_column_counts", normalize_table_column_counts),
    PostprocessRule("repair_shifted_disciplinary_table_rows", repair_shifted_disciplinary_table_rows),
    PostprocessRule("repair_continued_tables_across_pages", repair_continued_tables_across_pages),
)


def run_postprocess_pipeline(
    markdown: str,
    rules: Iterable[PostprocessRule] = DEFAULT_POSTPROCESS_RULES,
) -> str:
    text = str(markdown or "")
    for rule in rules:
        text = rule.apply(text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return lam_sach_text(text) + "\n"


def postprocess_final_markdown(markdown: str) -> str:
    """Run the default OCR Markdown postprocess pipeline."""
    return run_postprocess_pipeline(markdown)
