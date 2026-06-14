"""
document_page_analyzer.py

Nhận diện trang có bảng/lưu đồ/biểu mẫu thật để router quyết định khi nào cần gọi LlamaParse.
Module này CHỈ PHÂN TÍCH layout, tuyệt đối không trích bảng bằng PyMuPDF.

Mục tiêu:
- Trang văn bản thường -> dùng PyMuPDF text/Paddle+VietOCR local.
- Trang có bảng/lưu đồ/ô kẻ thật -> dùng LlamaParse để xuất bảng Markdown.
- Trang biểu mẫu có nhiều dòng chấm/checkbox/trường điền -> dùng LlamaParse/spatial layout.
- Không tạo bảng khi file gốc không có bảng.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import fitz  # PyMuPDF


@dataclass
class PageLayoutSignal:
    """Kết quả phân tích layout của một trang PDF.

    page_number: số trang 1-based.
    likely_table: True nếu có đủ bằng chứng trang có bảng/lưu đồ thật.
    likely_form: True nếu có đủ bằng chứng trang là biểu mẫu cần giữ layout.
    reasons: các lý do giúp debug vì sao trang bị route sang LlamaParse.
    """

    page_number: int
    likely_table: bool
    text_chars: int
    vector_line_count: int = 0
    raster_line_score: float = 0.0
    raster_form_score: float = 0.0
    raster_horizontal_lines: int = 0
    raster_vertical_lines: int = 0
    keyword_score: int = 0
    form_score: int = 0
    likely_form: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class RasterLayoutScore:
    """Điểm layout từ ảnh render ở DPI thấp."""

    table_score: float = 0.0
    form_score: float = 0.0
    horizontal_lines: int = 0
    vertical_lines: int = 0


def normalize_text_for_match(text: str) -> str:
    """Chuẩn hóa text nhẹ để so khớp keyword layout."""
    text = str(text or "").lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def count_vector_line_items(page: fitz.Page) -> int:
    """Đếm số đường kẻ vector trong trang PDF."""
    try:
        drawings = page.get_drawings()
    except Exception:
        return 0

    count = 0
    for drawing in drawings:
        for item in drawing.get("items", []):
            kind = item[0]
            if kind in {"l", "c", "qu"}:  # line, curve, quad/shape
                count += 1
    return count


def keyword_score_for_table_or_flow(text: str) -> tuple[int, list[str]]:
    """Tính điểm keyword cho trang có bảng/lưu đồ thật.

    Rule vẫn chặt để tránh false positive: cần nhiều header/cụm đặc trưng của bảng,
    không chỉ dựa vào các mục `1.`, `a)` trong văn bản thường.
    """
    t = normalize_text_for_match(text)
    score = 0
    reasons: list[str] = []

    strong_phrases = [
        "ii. lưu đồ",
        "lưu đồ",
        "khung kế hoạch thực hiện",
        "số lần vi phạm",
        "hình thức xử lý",
        "doanh số cho vay",
        "doanh số thu nợ",
        "dư nợ",
        "số khách hàng",
    ]
    header_terms = [
        "bước",
        "nội dung công việc",
        "người thực hiện",
        "thời gian thực hiện",
        "ghi chú",
        "đơn vị",
        "phối hợp",
        "tt",
        "nội dung vi phạm",
        "lần 1",
        "lần 2",
        "lần 3",
        "phân loại",
        "trong kỳ báo cáo",
        "lũy kế",
        "nợ quá hạn",
    ]

    matched_strong = [p for p in strong_phrases if p in t]
    if matched_strong:
        score += 2 + len(matched_strong)
        reasons.append("keyword_table_strong:" + ",".join(matched_strong[:4]))

    matched_headers = [term for term in header_terms if term in t]
    if len(matched_headers) >= 3:
        score += len(matched_headers)
        reasons.append("many_table_header_terms:" + ",".join(matched_headers[:6]))

    if "hồ sơ đạt" in t and "hồ sơ không đạt" in t:
        score += 2
        reasons.append("flowchart_decision_labels")

    return score, reasons


def keyword_score_for_form(text: str) -> tuple[int, list[str]]:
    """Tính điểm keyword cho biểu mẫu/tờ khai.

    Áp dụng cho PDF text hoặc Llama text layer. Với PDF scan không có text, phần
    `raster_form_score` sẽ hỗ trợ nhận diện dòng chấm/checkbox.
    """
    t = normalize_text_for_match(text)
    score = 0
    reasons: list[str] = []

    strong = ["tờ khai", "mẫu", "phụ lục", "xác nhận của", "ký, ghi rõ", "đóng dấu"]
    fields = [
        "họ và tên",
        "ngày sinh",
        "giới tính",
        "cccd",
        "nơi cấp",
        "tên cơ sở giáo dục",
        "hệ đào tạo",
        "ngành, lĩnh vực đào tạo",
        "mã ngành",
        "loại hình đào tạo",
        "đồng/tháng",
        "người học",
    ]

    matched_strong = [x for x in strong if x in t]
    matched_fields = [x for x in fields if x in t]
    if matched_strong:
        score += 2 + len(matched_strong)
    if len(matched_fields) >= 3:
        score += len(matched_fields)

    if matched_strong:
        reasons.append("form_strong:" + ",".join(matched_strong[:4]))
    if matched_fields:
        reasons.append("form_fields:" + ",".join(matched_fields[:6]))

    # Dòng chấm thường thấy trong biểu mẫu PDF text.
    dot_lines = len(re.findall(r"\.{6,}", text or ""))
    if dot_lines >= 3:
        score += min(dot_lines, 8)
        reasons.append(f"many_dot_leaders:{dot_lines}")

    return score, reasons


def render_page_for_analysis(page: fitz.Page, dpi: int = 120) -> bytes:
    """Render trang PDF ở DPI thấp để phân tích đường kẻ raster."""
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return pix.tobytes("png")


def raster_layout_score(page: fitz.Page, dpi: int = 120) -> RasterLayoutScore:
    """Ước lượng bảng/biểu mẫu từ ảnh render.

    Bản cũ chỉ đếm tổng contour ngang+dọc nên dễ nhầm các dòng chữ đậm trong trang
    văn bản thành bảng. Bản này tách ngang/dọc:
    - Bảng thật cần cả đường ngang và dọc.
    - Biểu mẫu có thể có nhiều dòng ngang/dòng chấm nhưng ít đường dọc.
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return RasterLayoutScore()

    try:
        png_bytes = render_page_for_analysis(page, dpi=dpi)
        arr = np.frombuffer(png_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return RasterLayoutScore()

        binary = cv2.adaptiveThreshold(
            img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15
        )
        h, w = binary.shape[:2]

        # Kernel dài để giữ đường kẻ thật. Kernel này hạn chế nhận nhầm dòng chữ.
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(35, w // 12), 1))
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(35, h // 12)))
        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
        vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=1)

        h_contours, _ = cv2.findContours(horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        v_contours, _ = cv2.findContours(vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        h_count = 0
        for c in h_contours:
            x, y, cw, ch = cv2.boundingRect(c)
            if cw >= w * 0.22 and ch <= max(12, h * 0.02):
                h_count += 1

        v_count = 0
        for c in v_contours:
            x, y, cw, ch = cv2.boundingRect(c)
            if ch >= h * 0.12 and cw <= max(12, w * 0.02):
                v_count += 1

        # Bảng thật thường có cả ngang và dọc. Nếu thiếu dọc, table_score bị chặn thấp.
        if h_count >= 4 and v_count >= 3:
            table_score = min(h_count / 18.0, 1.0) * 0.45 + min(v_count / 12.0, 1.0) * 0.55
        else:
            table_score = min(h_count / 30.0, 0.25) + min(v_count / 20.0, 0.20)

        # Form/tờ khai thường có nhiều đường ngang/dòng chấm nhưng không nhất thiết có dọc.
        form_score = 0.0
        if h_count >= 6:
            form_score = min(h_count / 18.0, 1.0)
            if v_count >= 3:
                form_score = min(form_score + 0.15, 1.0)

        return RasterLayoutScore(table_score=table_score, form_score=form_score, horizontal_lines=h_count, vertical_lines=v_count)
    except Exception:
        return RasterLayoutScore()


def analyze_page(page: fitz.Page, page_number: int) -> PageLayoutSignal:
    """Phân tích một trang PDF và quyết định có khả năng là bảng/form thật không."""
    raw_text = page.get_text("text") or ""
    vector_lines = count_vector_line_items(page)
    raster = raster_layout_score(page)
    k_score, k_reasons = keyword_score_for_table_or_flow(raw_text)
    f_score, f_reasons = keyword_score_for_form(raw_text)

    reasons: list[str] = []
    reasons.extend(k_reasons)
    reasons.extend(f_reasons)
    if vector_lines >= 20:
        reasons.append(f"many_vector_lines:{vector_lines}")
    if raster.table_score >= 0.45:
        reasons.append(f"raster_table_score:{raster.table_score:.2f}")
    if raster.form_score >= 0.45:
        reasons.append(f"raster_form_score:{raster.form_score:.2f}")
    if raster.horizontal_lines or raster.vertical_lines:
        reasons.append(f"raster_lines:h{raster.horizontal_lines}/v{raster.vertical_lines}")

    likely_table = False
    if k_score >= 3 and (vector_lines >= 8 or raster.table_score >= 0.30):
        likely_table = True
    elif vector_lines >= 45:
        likely_table = True
    elif raster.table_score >= 0.70:
        likely_table = True

    likely_form = False
    if not likely_table:
        if f_score >= 5 and (raster.form_score >= 0.25 or vector_lines >= 8 or len(raw_text.strip()) > 80):
            likely_form = True
        elif raster.form_score >= 0.80 and raster.vertical_lines < 5:
            likely_form = True

    # Trang có bảng lớn cũng có thể là biểu mẫu bảng; route vẫn qua LlamaParse bằng likely_table.
    return PageLayoutSignal(
        page_number=page_number,
        likely_table=likely_table,
        likely_form=likely_form,
        text_chars=len(raw_text.strip()),
        vector_line_count=vector_lines,
        raster_line_score=raster.table_score,
        raster_form_score=raster.form_score,
        raster_horizontal_lines=raster.horizontal_lines,
        raster_vertical_lines=raster.vertical_lines,
        keyword_score=k_score,
        form_score=f_score,
        reasons=reasons,
    )


def page_range(total_pages: int, page_start: Optional[int], page_end: Optional[int]) -> range:
    """Tạo range index trang 0-based từ page_start/page_end 1-based."""
    start = max(1, int(page_start or 1))
    end = int(page_end or total_pages)
    end = min(end, total_pages)
    if end < start:
        end = start
    return range(start - 1, end)


def analyze_pdf_pages(
    pdf_path: str | Path,
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
) -> list[PageLayoutSignal]:
    """Phân tích các trang PDF để tìm trang cần LlamaParse xử lý bảng/form."""
    path = Path(pdf_path)
    if path.suffix.lower() != ".pdf":
        return []

    doc = fitz.open(str(path))
    try:
        signals: list[PageLayoutSignal] = []
        for idx in page_range(len(doc), page_start, page_end):
            signals.append(analyze_page(doc[idx], idx + 1))
        return signals
    finally:
        doc.close()


def group_contiguous_pages(pages: Iterable[int]) -> list[tuple[int, int]]:
    """Gộp danh sách trang 1-based thành các khoảng liên tiếp."""
    sorted_pages = sorted(set(int(p) for p in pages))
    if not sorted_pages:
        return []

    groups: list[tuple[int, int]] = []
    start = prev = sorted_pages[0]
    for page in sorted_pages[1:]:
        if page == prev + 1:
            prev = page
        else:
            groups.append((start, prev))
            start = prev = page
    groups.append((start, prev))
    return groups


def is_table_continuation_signal(signal: PageLayoutSignal) -> bool:
    """Nhận diện trang liền kề có khả năng là phần tiếp nối của bảng."""
    if signal.likely_table:
        return True

    # Bảng text-PDF thường có nhiều vector line. Với file Nội quy KTX, trang 4/6 có ~32/33.
    if signal.vector_line_count >= 25:
        return True

    # Với PDF scan, chỉ mở rộng khi có cả dấu hiệu ngang/dọc, tránh trang văn bản thường.
    if signal.raster_line_score >= 0.55 and signal.raster_vertical_lines >= 3:
        return True

    if signal.keyword_score >= 2 and (signal.vector_line_count >= 10 or signal.raster_line_score >= 0.30):
        return True

    return False


def table_pages_from_signals(
    signals: list[PageLayoutSignal],
    expand_contiguous_tables: bool = True,
) -> list[int]:
    """Lấy danh sách trang cần dùng LlamaParse.

    Danh sách gồm:
    - Trang bảng/lưu đồ thật.
    - Trang biểu mẫu/tờ khai cần spatial layout.
    - Trang bảng liền kề cần mở rộng để không mất header/cột ở bảng nhiều trang.
    """

    if not signals:
        return []

    direct_pages = {s.page_number for s in signals if s.likely_table or s.likely_form}
    table_direct_pages = {s.page_number for s in signals if s.likely_table}
    if not direct_pages or not expand_contiguous_tables:
        return sorted(direct_pages)

    by_page = {s.page_number: s for s in signals}
    selected = set(direct_pages)

    for page in sorted(table_direct_pages):
        for step in (-1, 1):
            cur = page + step
            while cur in by_page and is_table_continuation_signal(by_page[cur]):
                selected.add(cur)
                cur += step

    return sorted(selected)
