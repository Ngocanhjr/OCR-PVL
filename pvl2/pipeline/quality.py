"""
Quality checks for OCR/parser output.

This module is intentionally heuristic and small. It does not repair content.
It only scores page output so the router can retry with a stronger extractor or
mark the page for review.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


TABLE_HEADER_HINTS = {
    "bước",
    "lưu đồ",
    "nội dung",
    "công việc",
    "người",
    "thực hiện",
    "thời gian",
    "ghi chú",
    "đơn vị",
    "phối hợp",
    "hồ sơ",
}

IMPORTANT_COLUMN_HINTS = {
    "lưu đồ",
    "nội dung",
    "công việc",
    "người",
    "thực hiện",
    "thời gian",
}

DANGLING_WORDS = {
    "và",
    "hoặc",
    "với",
    "của",
    "cho",
    "để",
    "về",
    "tại",
    "thông",
    "kiểm",
    "khám",
}


@dataclass
class TableQualityAssessment:
    page: int
    score: float
    status: str
    issues: list[str]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_table_separator(line: str) -> bool:
    return bool(re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$", line))


def _split_table_row(line: str) -> list[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    return [re.sub(r"\s+", " ", cell).strip() for cell in value.split("|")]


def _normalize(value: str) -> str:
    value = value.lower()
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[*_`#;:,.()\\[\\]]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _word_count(value: str) -> int:
    return len(re.findall(r"[A-Za-zÀ-ỹĐđ0-9]+", value))


def _table_blocks(markdown: str) -> list[list[str]]:
    lines = markdown.splitlines()
    blocks: list[list[str]] = []
    i = 0
    while i < len(lines):
        if "|" not in lines[i] or lines[i].lstrip().startswith("<!--"):
            i += 1
            continue

        block: list[str] = []
        j = i
        saw_separator = False
        while j < len(lines):
            line = lines[j]
            if not line.strip():
                break
            if "|" not in line and not _is_table_separator(line):
                break
            block.append(line)
            saw_separator = saw_separator or _is_table_separator(line)
            j += 1

        if len(block) >= 2 and saw_separator:
            blocks.append(block)
            i = j
        else:
            i += 1
    return blocks


def _header_and_rows(table: list[str]) -> tuple[list[str], list[list[str]]]:
    header: list[str] = []
    rows: list[list[str]] = []
    for line in table:
        if _is_table_separator(line):
            continue
        cells = _split_table_row(line)
        if not header:
            header = cells
        else:
            rows.append(cells)
    return header, rows


def _has_header_hints(header: list[str]) -> bool:
    header_text = _normalize(" ".join(header))
    return sum(1 for hint in TABLE_HEADER_HINTS if hint in header_text) >= 2


def _important_indexes(header: list[str]) -> list[int]:
    indexes: list[int] = []
    for index, cell in enumerate(header):
        text = _normalize(cell)
        if any(hint in text for hint in IMPORTANT_COLUMN_HINTS):
            indexes.append(index)
    return indexes


def _looks_truncated(cell: str) -> bool:
    text = _normalize(cell)
    if not text:
        return False
    words = text.split()
    if len(words) <= 2 and cell.rstrip().endswith(";"):
        return True
    if words and words[-1] in DANGLING_WORDS and _word_count(text) <= 6:
        return True
    if cell.count("(") != cell.count(")") or cell.count("[") != cell.count("]"):
        return True
    return False


def assess_table_page(markdown: str, page: int, min_score: float = 0.86) -> TableQualityAssessment:
    """Score one page that is expected to contain a table/flow layout."""
    tables = _table_blocks(markdown)
    issues: list[str] = []
    details: dict[str, Any] = {
        "table_count": len(tables),
        "rows": 0,
        "columns": [],
        "suspicious_cells": [],
    }

    if not tables:
        return TableQualityAssessment(
            page=page,
            score=0.20,
            status="needs_review",
            issues=["missing_markdown_table"],
            details=details,
        )

    score = 1.0
    for table_index, table in enumerate(tables, start=1):
        header, rows = _header_and_rows(table)
        expected_cols = len(header)
        row_lengths = [len(row) for row in rows]
        details["rows"] += len(rows)
        details["columns"].append(expected_cols)

        if expected_cols < 3:
            issues.append(f"table_{table_index}_too_few_columns")
            score -= 0.20

        if not _has_header_hints(header):
            issues.append(f"table_{table_index}_weak_header")
            score -= 0.15

        if rows:
            mismatch = sum(1 for length in row_lengths if length != expected_cols)
            mismatch_ratio = mismatch / len(rows)
            if mismatch_ratio >= 0.20:
                issues.append(f"table_{table_index}_row_cell_count_mismatch")
                score -= min(0.25, mismatch_ratio)

        important_indexes = _important_indexes(header)
        empty_important = 0
        important_cells = 0
        suspicious_count = 0
        for row_no, row in enumerate(rows, start=1):
            for col_index in important_indexes:
                if col_index >= len(row):
                    continue
                important_cells += 1
                cell = row[col_index].strip()
                if not cell:
                    empty_important += 1
                if _looks_truncated(cell):
                    suspicious_count += 1
                    if len(details["suspicious_cells"]) < 8:
                        details["suspicious_cells"].append(
                            {
                                "table": table_index,
                                "row": row_no,
                                "column": header[col_index],
                                "text": cell[:120],
                            }
                        )

        if important_cells:
            empty_ratio = empty_important / important_cells
            if empty_ratio >= 0.15:
                issues.append(f"table_{table_index}_empty_important_cells")
                score -= min(0.20, empty_ratio)

        if suspicious_count:
            issues.append(f"table_{table_index}_possible_truncated_cells")
            score -= min(0.30, 0.15 * suspicious_count)

    score = max(0.0, min(1.0, round(score, 3)))
    status = "ok" if score >= min_score else "needs_review"
    return TableQualityAssessment(page=page, score=score, status=status, issues=sorted(set(issues)), details=details)


def assess_table_pages(
    page_blocks: dict[int, str],
    pages: list[int],
    min_score: float = 0.86,
) -> dict[int, TableQualityAssessment]:
    return {
        page: assess_table_page(page_blocks.get(page, ""), page=page, min_score=min_score)
        for page in pages
    }


def assessments_to_report(assessments: dict[int, TableQualityAssessment]) -> list[dict[str, Any]]:
    return [assessments[page].to_dict() for page in sorted(assessments)]
