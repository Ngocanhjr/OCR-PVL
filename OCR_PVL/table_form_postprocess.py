"""
table_form_postprocess.py

Hậu xử lý chung cho bảng và biểu mẫu sau khi OCR/LlamaParse trả Markdown.

Mục tiêu:
- Không hardcode theo một file cụ thể.
- Sửa các lỗi lặp lại ở nhiều văn bản hành chính: watermark scanner, bảng bị mất header,
  bảng nhiều trang bị mất header ở trang sau, biểu mẫu có dòng chấm/checkbox bị rối.
- Ưu tiên giữ cấu trúc an toàn cho RAG hơn là đoán dữ liệu pháp lý chưa chắc chắn.
"""

from __future__ import annotations

import re
from typing import Iterable

from config import lam_sach_dong, lam_sach_text, chuan_hoa_de_so_khop
from page_markers import PAGE_BOUNDARY_RE, is_page_boundary_line, normalize_legacy_page_headings


_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


SCANNER_WATERMARK_PATTERNS = [
    r"^\s*scanned\s+with\s+(cs\s*)?camscanner\s*$",
    r"^\s*scanned\s+with\s+cs\s*$",
    r"^\s*camscanner\s*$",
]


def remove_scanner_watermarks(text: str) -> str:
    """Xóa watermark phổ biến của app scan, tránh đưa nhiễu vào RAG."""
    kept: list[str] = []
    for raw in str(text or "").splitlines():
        line = lam_sach_dong(raw)
        if any(re.match(p, line, flags=re.IGNORECASE) for p in SCANNER_WATERMARK_PATTERNS):
            continue
        kept.append(raw.rstrip())
    return "\n".join(kept)


def split_table_row(line: str) -> list[str]:
    """Tách một dòng markdown table thành cell."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [re.sub(r"\s+", " ", c).strip() for c in s.split("|")]


def make_table_row(cells: Iterable[str], ncols: int | None = None) -> str:
    """Tạo lại markdown table row, tự pad cell rỗng nếu cần."""
    cells = [str(c).strip() for c in cells]
    if ncols is not None:
        if len(cells) < ncols:
            cells = cells + [""] * (ncols - len(cells))
        elif len(cells) > ncols:
            # Không bỏ dữ liệu: gộp phần dư vào cột cuối.
            cells = cells[: ncols - 1] + [" ".join(cells[ncols - 1 :]).strip()]
    return "| " + " | ".join(cells) + " |"


def make_separator(ncols: int) -> str:
    return "| " + " | ".join(["---"] * max(1, ncols)) + " |"


def is_table_separator(line: str) -> bool:
    return bool(_TABLE_SEPARATOR_RE.match(line or ""))


def is_table_row(line: str) -> bool:
    return bool(_TABLE_ROW_RE.match(line or "")) and not is_table_separator(line)


def is_probably_data_header_row(cells: list[str]) -> bool:
    """Nhận diện lỗi: dòng dữ liệu đầu tiên bị LlamaParse lấy làm header bảng."""
    if len(cells) < 3:
        return False
    first = cells[0].strip()
    second = cells[1].strip() if len(cells) > 1 else ""
    # Các bảng biểu hành chính thường có cột đầu là TT/STT: 01, 05, 9, I, II...
    first_is_index = bool(re.match(r"^(\d{1,3}|[IVXLCDM]+)$", first, flags=re.IGNORECASE))
    second_has_sentence = len(second.split()) >= 3
    known_action_words = re.search(
        r"\b(KTX|khiển trách|cảnh cáo|buộc ra khỏi|vi phạm|phân loại|khối ngành|cấp học|công nghệ|thạc sĩ|đại học)\b",
        " ".join(cells),
        flags=re.IGNORECASE,
    )
    return first_is_index and second_has_sentence and bool(known_action_words)


def guess_generic_header(cells: list[str]) -> list[str]:
    """Đoán header bảng ở mức an toàn, chỉ dựa vào cấu trúc chung."""
    ncols = len(cells)
    joined_key = chuan_hoa_de_so_khop(" ".join(cells))

    # Bảng xử lý kỷ luật/nội quy KTX hay có 6 cột: TT, nội dung, lần 1-3, ghi chú.
    if ncols == 6 and any(k in joined_key for k in ["ktx", "khien trach", "canh cao", "buoc ra khoi", "vi pham"]):
        return ["TT", "Nội dung vi phạm", "Lần 1", "Lần 2", "Lần 3", "Ghi chú"]

    # Bảng báo cáo Phụ lục III của quyết định vay vốn có nhiều cột.
    if ncols >= 10 and any(k in joined_key for k in ["doanh so", "du no", "khach hang", "phan loai"]):
        return [f"Cột {i}" for i in range(1, ncols + 1)]

    if ncols >= 3:
        return ["TT", "Nội dung"] + [f"Cột {i}" for i in range(3, ncols + 1)]
    return [f"Cột {i}" for i in range(1, ncols + 1)]


def repair_data_row_used_as_header(markdown: str) -> str:
    """Sửa bảng có dòng đầu là data nhưng bị đặt trước separator như header."""
    lines = markdown.split("\n")
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
    """Pad/gộp số cột trong từng markdown table để bảng không bị vỡ khi render."""
    lines = markdown.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not is_table_row(lines[i]):
            out.append(lines[i])
            i += 1
            continue

        # Lấy block table liên tục.
        block: list[str] = []
        j = i
        while j < len(lines) and (is_table_row(lines[j]) or is_table_separator(lines[j]) or not lines[j].strip()):
            if not lines[j].strip():
                # Chỉ giữ dòng trống nếu bảng đã kết thúc.
                break
            block.append(lines[j])
            j += 1

        rows = [split_table_row(x) for x in block if is_table_row(x)]
        if len(block) >= 2 and rows:
            # Ưu tiên số cột của header, nếu không có thì lấy max.
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


def extract_last_table_header(block: str) -> tuple[list[str], int] | None:
    """Lấy header của bảng cuối trong một block trang."""
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
    """Trang có vẻ tiếp tục bảng nhưng thiếu header."""
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--") or is_page_boundary_line(line):
            continue
        # Bỏ qua số trang in trong nội dung OCR/LlamaParse.
        if re.match(r"^\d{1,3}$", line):
            continue
        if is_table_row(line):
            return True
        if re.match(r"^(\d{1,3}|[IVXLCDM]+|Tổng cộng)\s+\S+", line, flags=re.IGNORECASE):
            return True
        return False
    return False


def line_to_continued_table_row(line: str, ncols: int) -> str | None:
    """Chuyển dòng text rời ở trang tiếp theo thành row bảng đơn giản nếu an toàn."""
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
    """Kế thừa header cho bảng nhiều trang khi trang sau bị mất header.

    Rule chỉ áp dụng trong phạm vi từng `<!-- page: n -->` và khi trang sau bắt đầu bằng table row
    hoặc dòng chỉ mục kiểu `9 Công nghệ tài chính`.
    """
    parts = PAGE_BOUNDARY_RE.split(normalize_legacy_page_headings(markdown))
    if len(parts) <= 1:
        return markdown

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
                if not inserted and s and not s.startswith("<!--") and not is_page_boundary_line(s) and not re.match(r"^\d{1,3}$", s):
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


def normalize_form_layout(markdown: str) -> str:
    """Làm biểu mẫu OCR dễ đọc hơn mà không đoán nội dung điền vào.

    - Giữ dòng chấm thành placeholder gọn hơn.
    - Chuẩn hóa checkbox rời `0`, `O`, `□` thành `[ ]` khi đi cùng các nhãn Có/Không/Nam/Nữ.
    """
    text = markdown
    text = re.sub(r"\.{6,}", "________", text)
    text = re.sub(r"\s+…{2,}", " ________", text)

    # Checkbox OCR hay thành O/0/□ nằm sát nhãn.
    text = re.sub(r"\b(Nam|Nữ|Có|Không)\s+[O0□☐]\b", r"\1 [ ]", text, flags=re.IGNORECASE)
    text = re.sub(r"[O0□☐]\s+(Nam|Nữ|Có|Không)\b", r"[ ] \1", text, flags=re.IGNORECASE)

    # Các trường biểu mẫu nên đứng riêng dòng nếu bị dính sau dấu chấm/placeholder.
    text = re.sub(r"(__+)\s+(Họ và tên|Ngày sinh|Giới tính|CCCD|Nơi cấp|Tên cơ sở|Hệ đào tạo|Ngành|Mã ngành|Loại hình đào tạo)", r"\1\n\2", text, flags=re.IGNORECASE)
    return text


def postprocess_final_markdown(markdown: str) -> str:
    """Chạy toàn bộ hậu xử lý bảng/biểu mẫu chung cho output cuối."""
    text = normalize_legacy_page_headings(remove_scanner_watermarks(markdown))
    text = normalize_form_layout(text)
    text = repair_data_row_used_as_header(text)
    text = normalize_table_column_counts(text)
    text = repair_continued_tables_across_pages(text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return lam_sach_text(text) + "\n"
