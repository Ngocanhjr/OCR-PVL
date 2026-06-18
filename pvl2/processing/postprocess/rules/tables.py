from __future__ import annotations

import re
from typing import Iterable

from config import chuan_hoa_de_so_khop, lam_sach_dong
from processing.page_markers import PAGE_BOUNDARY_RE, PAGE_MARKER_RE


_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_CELL_HTML_BREAK_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
_TABLE_CELL_DASH_BREAK_RE = re.compile(r"\s*-{4,}\s*")
_TABLE_CELL_BREAK_SEPARATOR = "; "


def split_table_row(line: str) -> list[str]:
    s = str(line or "").strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [re.sub(r"\s+", " ", c).strip() for c in s.split("|")]


def normalize_table_cell_breaks(value: str) -> str:
    text = str(value).strip()
    text = _TABLE_CELL_HTML_BREAK_RE.sub(_TABLE_CELL_BREAK_SEPARATOR, text)
    text = _TABLE_CELL_DASH_BREAK_RE.sub(_TABLE_CELL_BREAK_SEPARATOR, text)
    text = re.sub(r"\s*;\s*", "; ", text)
    return re.sub(r"(?:;\s*){2,}", "; ", text).strip(" ;")


def make_table_row(cells: Iterable[str], ncols: int | None = None) -> str:
    cells = [normalize_table_cell_breaks(str(c)) for c in cells]
    if ncols is not None:
        if len(cells) < ncols:
            cells = cells + [""] * (ncols - len(cells))
        elif len(cells) > ncols:
            cells = cells[: ncols - 1] + [" ".join(cells[ncols - 1 :]).strip()]
    return "| " + " | ".join(cells) + " |"


def make_separator(ncols: int) -> str:
    return "| " + " | ".join(["---"] * max(1, ncols)) + " |"


def is_table_separator(line: str) -> bool:
    return bool(_TABLE_SEPARATOR_RE.match(line or ""))


def is_table_row(line: str) -> bool:
    return bool(_TABLE_ROW_RE.match(line or "")) and not is_table_separator(line)


def is_probably_data_header_row(cells: list[str]) -> bool:
    if len(cells) < 3:
        return False
    first = cells[0].strip()
    second = cells[1].strip() if len(cells) > 1 else ""
    first_is_index = bool(re.match(r"^(\d{1,3}|[IVXLCDM]+)$", first, flags=re.IGNORECASE))
    second_has_sentence = len(second.split()) >= 3
    known_action_words = re.search(
        r"\b(KTX|khiển trách|cảnh cáo|buộc ra khỏi|vi phạm|phân loại|khối ngành|cấp học|công nghệ|thạc sĩ|đại học)\b",
        " ".join(cells),
        flags=re.IGNORECASE,
    )
    return first_is_index and second_has_sentence and bool(known_action_words)


def guess_generic_header(cells: list[str]) -> list[str]:
    ncols = len(cells)
    joined_key = chuan_hoa_de_so_khop(" ".join(cells))
    if ncols == 6 and any(k in joined_key for k in ["ktx", "khien trach", "canh cao", "buoc ra khoi", "vi pham"]):
        return ["TT", "Nội dung vi phạm", "Lần 1", "Lần 2", "Lần 3", "Ghi chú"]
    if ncols >= 10 and any(k in joined_key for k in ["doanh so", "du no", "khach hang", "phan loai"]):
        return [f"Cột {i}" for i in range(1, ncols + 1)]
    if ncols >= 3:
        return ["TT", "Nội dung"] + [f"Cột {i}" for i in range(3, ncols + 1)]
    return [f"Cột {i}" for i in range(1, ncols + 1)]


def repair_data_row_used_as_header(markdown: str) -> str:
    lines = str(markdown or "").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if is_table_row(line) and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            cells = split_table_row(line)
            if is_probably_data_header_row(cells):
                header = guess_generic_header(cells)
                ncols = max(len(header), len(cells))
                out.append(make_table_row(header, ncols))
                out.append(make_separator(ncols))
                out.append(make_table_row(cells, ncols))
                i += 2
                continue
        out.append(line)
        i += 1
    return "\n".join(out)


def normalize_table_column_counts(markdown: str) -> str:
    lines = str(markdown or "").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not is_table_row(lines[i]):
            out.append(lines[i])
            i += 1
            continue

        block: list[str] = []
        j = i
        while j < len(lines) and (is_table_row(lines[j]) or is_table_separator(lines[j]) or not lines[j].strip()):
            if not lines[j].strip():
                break
            block.append(lines[j])
            j += 1

        rows = [split_table_row(x) for x in block if is_table_row(x)]
        if len(block) >= 2 and rows:
            header_cols = len(rows[0])
            max_cols = max(len(r) for r in rows)
            ncols = max(header_cols, max_cols)
            for row_line in block:
                if is_table_separator(row_line):
                    out.append(make_separator(ncols))
                elif is_table_row(row_line):
                    out.append(make_table_row(split_table_row(row_line), ncols))
                else:
                    out.append(row_line)
        else:
            out.extend(block)
        i = j
    return "\n".join(out)


def looks_like_index_cell(value: str) -> bool:
    return bool(re.match(r"^\s*(\d{1,3}|[IVXLCDM]+)\s*$", str(value or ""), flags=re.IGNORECASE))


def looks_like_action_cell(value: str) -> bool:
    return bool(
        re.search(
            r"\b(nhắc nhở|khiển trách|cảnh cáo|buộc ra khỏi|bồi thường|truy thu|đề nghị|xử lý)\b",
            str(value or ""),
            flags=re.IGNORECASE,
        )
    )


def repair_shifted_disciplinary_table_rows(markdown: str) -> str:
    lines = str(markdown or "").split("\n")
    out: list[str] = []
    in_disciplinary_table = False
    expected_cols = 0

    for line in lines:
        if is_table_separator(line):
            out.append(line)
            continue

        if not is_table_row(line):
            out.append(line)
            if line.strip():
                in_disciplinary_table = False
                expected_cols = 0
            continue

        cells = split_table_row(line)
        key = chuan_hoa_de_so_khop(" ".join(cells))
        if {"tt", "noi dung vi pham", "lan 1"}.issubset(set(key.split())) or (
            "noi dung vi pham" in key and "lan 1" in key and "lan 2" in key
        ):
            in_disciplinary_table = True
            expected_cols = len(cells)
            out.append(line)
            continue

        if (
            in_disciplinary_table
            and expected_cols == 6
            and len(cells) == 6
            and cells[0]
            and not looks_like_index_cell(cells[0])
            and looks_like_action_cell(cells[1])
        ):
            out.append(make_table_row(["", cells[0], cells[1], cells[2], cells[3], cells[4]], expected_cols))
            continue

        out.append(line)

    return "\n".join(out)


def extract_last_table_header(block: str) -> tuple[list[str], int] | None:
    lines = block.split("\n")
    last: tuple[list[str], int] | None = None
    for i in range(len(lines) - 1):
        if is_table_row(lines[i]) and is_table_separator(lines[i + 1]):
            cells = split_table_row(lines[i])
            if cells:
                last = (cells, len(cells))
    return last


def page_has_table_header(block: str) -> bool:
    lines = block.split("\n")
    return any(is_table_row(lines[i]) and i + 1 < len(lines) and is_table_separator(lines[i + 1]) for i in range(len(lines)))


def starts_with_table_continuation(block: str) -> bool:
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--") or bool(PAGE_MARKER_RE.fullmatch(line.strip())):
            continue
        if re.match(r"^\d{1,3}$", line):
            continue
        if is_table_row(line):
            return True
        if re.match(r"^(\d{1,3}|[IVXLCDM]+|Tổng cộng)\s+\S+", line, flags=re.IGNORECASE):
            return True
        return False
    return False


def line_to_continued_table_row(line: str, ncols: int) -> str | None:
    s = lam_sach_dong(line)
    if not s or s.startswith("<!--") or s.startswith("##") or s.startswith("#"):
        return None
    if is_table_row(s):
        return make_table_row(split_table_row(s), ncols)

    m = re.match(r"^(\d{1,3}|[IVXLCDM]+)\s+(.+)$", s, flags=re.IGNORECASE)
    if m:
        return make_table_row([m.group(1), m.group(2)], ncols)
    if re.match(r"^Tổng cộng\.?$", s, flags=re.IGNORECASE):
        return make_table_row(["", "Tổng cộng"], ncols)
    return None


def repair_continued_tables_across_pages(markdown: str) -> str:
    parts = PAGE_BOUNDARY_RE.split(str(markdown or ""))
    if len(parts) <= 1:
        return str(markdown or "")

    rebuilt: list[str] = []
    last_header: tuple[list[str], int] | None = None
    previous_was_table = False

    for part in parts:
        if not part.strip():
            rebuilt.append(part)
            continue

        current = part
        has_header = page_has_table_header(current)
        if has_header:
            last_header = extract_last_table_header(current) or last_header
            previous_was_table = True
            rebuilt.append(current)
            continue

        if previous_was_table and last_header and starts_with_table_continuation(current):
            header_cells, ncols = last_header
            lines = current.split("\n")
            out: list[str] = []
            inserted = False
            for raw in lines:
                s = raw.strip()
                if not inserted and s and not s.startswith("<!--") and not bool(PAGE_MARKER_RE.fullmatch(s)) and not re.match(r"^\d{1,3}$", s):
                    out.append(make_table_row(header_cells, ncols))
                    out.append(make_separator(ncols))
                    inserted = True
                converted = line_to_continued_table_row(raw, ncols)
                out.append(converted if converted else raw)
            current = "\n".join(out)
            previous_was_table = True
            rebuilt.append(current)
            continue

        previous_was_table = has_header
        rebuilt.append(current)

    return "".join(rebuilt)
