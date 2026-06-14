"""
hybrid_router.py

Router cấp tài liệu/file cho các input không đi theo luồng PDF TableSafe chính.

Phân ranh với `hybrid_page_router.py`:
- PDF từ CLI `main.py` luôn đi qua `hybrid_page_router.run_table_safe_pdf()`.
- File ảnh/DOCX/PPTX/XLSX/CSV/HTML khi cần LlamaParse đi qua `run_document_parse()`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from engines.llamaparse_engine import save_llamaparse_markdown, tao_llama_config


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DOCUMENT_EXTS = {".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".html"}


# =========================================================
# AUTO-DETECT ENGINE
# =========================================================


def _extract_pdf_text(pdf_path: Path, max_pages: int = 3) -> str:
    """Trả text thô từ vài trang đầu PDF, chuỗi rỗng nếu lỗi/không có text."""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        parts = [doc[i].get_text("text") or "" for i in range(min(len(doc), max_pages))]
        doc.close()
        return "\n".join(parts).strip()
    except Exception:
        return ""


def has_extractable_pdf_text(pdf_path: str | Path, min_chars: int = 80) -> bool:
    """Kiểm tra PDF có text copy được không bằng PyMuPDF."""
    path = Path(pdf_path)
    return path.suffix.lower() == ".pdf" and len(_extract_pdf_text(path)) >= min_chars


def looks_table_heavy(pdf_path: str | Path) -> bool:
    """Heuristic: nhiều dòng ngắn + nhiều số → khả năng cao là bảng/cột → ưu tiên LlamaParse."""
    path = Path(pdf_path)
    if path.suffix.lower() != ".pdf":
        return False
    lines = [ln.strip() for ln in _extract_pdf_text(path).splitlines() if ln.strip()]
    if not lines:
        return False
    short_ratio = sum(1 for ln in lines if len(ln) <= 30) / len(lines)
    number_ratio = sum(1 for ln in lines if re.search(r"\d", ln)) / len(lines)
    return short_ratio > 0.45 and number_ratio > 0.35


def should_use_llamaparse_auto(input_path: str | Path) -> bool:
    """Quy tắc tự chọn: scan/ảnh/bảng phức tạp → LlamaParse, PDF text thường → local."""
    path = Path(input_path)
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS or ext in {".docx", ".pptx", ".xlsx", ".csv", ".html"}:
        return True
    if ext == ".pdf":
        return not has_extractable_pdf_text(path) or looks_table_heavy(path)
    return ext in DOCUMENT_EXTS


# =========================================================
# LOCAL ADAPTER
# =========================================================


def run_local_paddle_vietocr(
    input_path: str | Path,
    output_path: str | Path,
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
) -> Path:
    """Adapter local: gọi đúng hàm xử lý (pdf/ảnh) từ main.py rồi ghi Markdown."""
    from config import DUOI_ANH, DUOI_PDF, cau_hinh_cho_thu_muc, ghi_text_unicode, tao_thu_muc_can_thiet
    from main import xu_ly_file_anh, xu_ly_pdf
    from normalization.ctu_terms import canh_bao_thuat_ngu_ctu
    from normalization.rare_fix import ghi_bao_cao_review, tao_bao_cao_review
    from validation.apply_metadata import ap_dung_va_xac_thuc_metadata

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cau_hinh = cau_hinh_cho_thu_muc(
        output_path.parent,
        trang_bat_dau=int(page_start or 0),
        trang_ket_thuc=int(page_end or 0),
    )
    tao_thu_muc_can_thiet(cau_hinh)

    ext = input_path.suffix.lower()
    if ext in DUOI_PDF:
        body, _ = xu_ly_pdf(input_path, cau_hinh)
    elif ext in DUOI_ANH:
        body, _ = xu_ly_file_anh(input_path, cau_hinh)
    else:
        raise ValueError(f"Định dạng local PadViet chưa hỗ trợ: {input_path.suffix}")

    final_md = ap_dung_va_xac_thuc_metadata(body, output_path, input_path, cau_hinh.ngon_ngu_ocr)
    ghi_text_unicode(output_path, final_md)

    if cau_hinh.dung_tu_dien_ctu or cau_hinh.dung_loi_rieng:
        extra_warnings = canh_bao_thuat_ngu_ctu(final_md) if cau_hinh.dung_tu_dien_ctu else []
        review_warnings = tao_bao_cao_review(final_md, extra_warnings)
        review_path = ghi_bao_cao_review(input_path, review_warnings, cau_hinh)
        if review_path:
            print(f"[REVIEW] Báo cáo dòng nghi ngờ: {review_path}")

    return output_path


# =========================================================
# DOCUMENT PARSE ENTRY
# =========================================================


def run_document_parse(
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
    """Entry point cấp tài liệu cho ảnh/doc. PDF từ CLI dùng hybrid_page_router."""
    engine = engine.lower().strip()
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if engine not in {"auto", "local", "llamaparse"}:
        raise ValueError("engine phải là: auto | local | llamaparse")

    use_llama = should_use_llamaparse_auto(input_path) if engine == "auto" else engine == "llamaparse"

    if use_llama:
        cfg = tao_llama_config(
            llama_tier=llama_tier, page_start=page_start, page_end=page_end,
            export_tables_as_xlsx=export_tables_as_xlsx, preserve_spatial_text=preserve_spatial_text,
            disable_cache=disable_cache, aggressive_tables=aggressive_tables,
            repair_false_tables=repair_false_tables,
        )
        return save_llamaparse_markdown(input_path, output_path, cfg)

    return run_local_paddle_vietocr(input_path, output_path, page_start, page_end)
