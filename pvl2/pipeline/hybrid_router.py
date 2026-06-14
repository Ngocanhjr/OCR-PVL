"""
hybrid_router.py

Router cấp tài liệu/file cho các input không đi theo luồng PDF TableSafe chính.

Phân ranh với `hybrid_page_router.py`:
- PDF từ CLI `main.py` luôn đi qua `hybrid_page_router.run_table_safe_pdf()`.
- File ảnh/DOCX/PPTX/XLSX/CSV/HTML khi dùng engine=llamaparse đi qua `run_document_parse()`.

engine="auto" đã được bỏ (CLI chỉ hỗ trợ auto-page / local / llamaparse).
Nếu cần tự detect engine, gọi `should_use_llamaparse_auto` sau khi import riêng.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from engines.llamaparse_engine import save_llamaparse_markdown, tao_llama_config


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
# DOCUMENT PARSE ENTRY (chỉ hỗ trợ engine=llamaparse hoặc local)
# =========================================================


def run_document_parse(
    input_path: str | Path,
    output_path: str | Path,
    engine: str = "llamaparse",
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
    llama_tier: str = "agentic",
    export_tables_as_xlsx: bool = False,
    preserve_spatial_text: bool = False,
    disable_cache: bool = False,
    aggressive_tables: bool = False,
    repair_false_tables: bool = True,
) -> Path:
    """Entry point cấp tài liệu cho ảnh/doc. PDF từ CLI dùng hybrid_page_router.

    engine: "llamaparse" (default) hoặc "local".
    engine="auto" đã bị bỏ — caller tự quyết định trước khi gọi hàm này.
    """
    engine = engine.lower().strip()
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if engine not in {"local", "llamaparse"}:
        raise ValueError("engine phải là: local | llamaparse")

    if engine == "llamaparse":
        cfg = tao_llama_config(
            llama_tier=llama_tier, page_start=page_start, page_end=page_end,
            export_tables_as_xlsx=export_tables_as_xlsx, preserve_spatial_text=preserve_spatial_text,
            disable_cache=disable_cache, aggressive_tables=aggressive_tables,
            repair_false_tables=repair_false_tables,
        )
        return save_llamaparse_markdown(input_path, output_path, cfg)

    return run_local_paddle_vietocr(input_path, output_path, page_start, page_end)
