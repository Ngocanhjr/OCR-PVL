"""
hybrid_router.py

Router chọn engine OCR/parser:
- local: dùng source PadViet hiện tại: main.py -> xu_ly_pdf/xu_ly_file_anh.
- llamaparse: dùng LlamaParse Agentic/Agentic Plus cho scan, bảng, layout khó.
- auto: tự chọn sơ bộ dựa trên PDF có text hay không và mật độ bảng.

File này đã được chỉnh theo source OCR_PadViet_main_new.zip:
- Không dùng `from ocr_engine import process_file` vì source PadViet không có hàm đó.
- Dùng các hàm thật trong main.py: xu_ly_pdf, xu_ly_file_anh, tao_metadata_markdown.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Optional

from llamaparse_engine import LlamaParseConfig, save_llamaparse_markdown


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DOCUMENT_EXTS = {".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".html"}


def has_extractable_pdf_text(pdf_path: str | Path, min_chars: int = 80, max_pages_check: int = 3) -> bool:
    """Kiểm tra PDF có text copy được không bằng PyMuPDF."""
    path = Path(pdf_path)
    if path.suffix.lower() != ".pdf":
        return False

    try:
        import fitz  # PyMuPDF
    except ImportError:
        return False

    try:
        doc = fitz.open(str(path))
        text_parts = []
        for i in range(min(len(doc), max_pages_check)):
            text_parts.append(doc[i].get_text("text") or "")
        doc.close()
        text = "\n".join(text_parts).strip()
        return len(text) >= min_chars
    except Exception:
        return False


def looks_table_heavy(pdf_path: str | Path, max_pages_check: int = 3) -> bool:
    """Heuristic đơn giản: nếu text có nhiều dấu hiệu bảng/cột thì ưu tiên LlamaParse."""
    path = Path(pdf_path)
    if path.suffix.lower() != ".pdf":
        return False

    try:
        import fitz
        doc = fitz.open(str(path))
        raw = []
        for i in range(min(len(doc), max_pages_check)):
            raw.append(doc[i].get_text("text") or "")
        doc.close()
        text = "\n".join(raw)
    except Exception:
        return False

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False

    # Dạng nhiều cột/bảng thường có nhiều dòng ngắn, nhiều số, nhiều khoảng trắng/cột.
    short_ratio = sum(1 for ln in lines if len(ln) <= 30) / max(len(lines), 1)
    number_ratio = sum(1 for ln in lines if re.search(r"\d", ln)) / max(len(lines), 1)
    return short_ratio > 0.45 and number_ratio > 0.35


def should_use_llamaparse_auto(input_path: str | Path) -> bool:
    """Quy tắc tự chọn: scan/ảnh/bảng phức tạp thì LlamaParse, PDF text thường thì local."""
    path = Path(input_path)
    ext = path.suffix.lower()

    if ext in IMAGE_EXTS:
        return True
    if ext in {".docx", ".pptx", ".xlsx", ".csv", ".html"}:
        return True
    if ext == ".pdf":
        if not has_extractable_pdf_text(path):
            return True
        if looks_table_heavy(path):
            return True
        return False

    return ext in DOCUMENT_EXTS


def run_local_paddle_vietocr(
    input_path: str | Path,
    output_path: str | Path,
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
) -> Path:
    """
    Adapter cho source PadViet hiện tại.

    Source OCR_PadViet_main_new.zip KHÔNG có hàm `process_file` trong ocr_engine.py.
    Hàm xử lý file thật nằm trong main.py, gồm:
    - xu_ly_pdf(...)
    - xu_ly_file_anh(...)
    - tao_metadata_markdown(...)

    Adapter này tự tạo cấu hình CauHinhOCR, gọi đúng hàm theo đuôi file,
    rồi ghi Markdown ra đúng `output_path` mà main.py yêu cầu.
    """
    from config import CAU_HINH_MAC_DINH, DUOI_ANH, DUOI_PDF, ghi_text_unicode, tao_thu_muc_can_thiet
    from ctu_terms import canh_bao_thuat_ngu_ctu
    from main import tao_metadata_markdown, xu_ly_file_anh, xu_ly_pdf
    from rare_fix import ghi_bao_cao_review, tao_bao_cao_review

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cau_hinh = replace(
        CAU_HINH_MAC_DINH,
        thu_muc_output=str(output_path.parent),
        thu_muc_anh_tam=str(output_path.parent / "temp_images"),
        thu_muc_bao_cao=str(output_path.parent / "review_reports"),
        trang_bat_dau=int(page_start or 0),
        trang_ket_thuc=int(page_end or 0),
    )
    tao_thu_muc_can_thiet(cau_hinh)

    ext = input_path.suffix.lower()
    if ext in DUOI_PDF:
        body, metadata = xu_ly_pdf(input_path, cau_hinh)
    elif ext in DUOI_ANH:
        body, metadata = xu_ly_file_anh(input_path, cau_hinh)
    else:
        raise ValueError(f"Định dạng local PadViet chưa hỗ trợ: {input_path.suffix}")

    final_md = tao_metadata_markdown(input_path, metadata, cau_hinh) + body
    ghi_text_unicode(output_path, final_md)

    if cau_hinh.dung_tu_dien_ctu or cau_hinh.dung_loi_rieng:
        extra_warnings = canh_bao_thuat_ngu_ctu(final_md) if cau_hinh.dung_tu_dien_ctu else []
        warnings = tao_bao_cao_review(final_md, extra_warnings)
        review_path = ghi_bao_cao_review(input_path, warnings, cau_hinh)
        if review_path:
            print(f"[REVIEW] Báo cáo dòng nghi ngờ: {review_path}")

    return output_path


def run_hybrid_parse(
    input_path: str | Path,
    output_path: str | Path,
    engine: str = "auto",
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
    llama_tier: str = "agentic",
    export_tables_as_xlsx: bool = False,
    preserve_spatial_text: bool = False,
    disable_cache: bool = False,
    aggressive_tables: bool = False,
    repair_false_tables: bool = True,
) -> Path:
    """Entry chính: chọn engine và trả ra file Markdown."""
    engine = engine.lower().strip()
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if engine not in {"auto", "local", "llamaparse"}:
        raise ValueError("engine phải là: auto | local | llamaparse")

    use_llama = should_use_llamaparse_auto(input_path) if engine == "auto" else engine == "llamaparse"

    if use_llama:
        cfg = LlamaParseConfig(
            tier=llama_tier,  # type: ignore[arg-type]
            page_start=page_start,
            page_end=page_end,
            export_tables_as_xlsx=export_tables_as_xlsx,
            preserve_spatial_text=preserve_spatial_text,
            disable_cache=disable_cache,
            aggressive_table_extraction=aggressive_tables,
            repair_false_tables=repair_false_tables,
            specialized_chart_parsing="agentic_plus" if llama_tier == "agentic_plus" else None,
        )
        return save_llamaparse_markdown(input_path, output_path, cfg)

    return run_local_paddle_vietocr(input_path, output_path, page_start, page_end)
