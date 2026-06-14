"""
main.py
File chạy chính cho OCR CTU sạch và dễ mở rộng.

Pipeline tổng quát:
1. PDF text -> PyMuPDF extract.
2. PDF scan / ảnh -> render ảnh -> PaddleOCR detect + VietOCR recognize.
3. Lớp 1: sửa lỗi OCR phổ biến trong văn bản hành chính.
4. Lớp 2: chuẩn hóa từ điển/thuật ngữ CTU.
5. Lớp 3: lỗi riêng/ít gặp -> cảnh báo review hoặc sửa bằng JSON ngoài source.
6. Gộp dòng, định dạng Markdown, ghi output + review report.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import fitz  # PyMuPDF

from config import (
    DUOI_ANH,
    CauHinhOCR,
    ghi_text_unicode,
    lam_sach_text,
    tao_thu_muc_can_thiet,
    ten_file_an_toan,
)
from processing.markdown_layout import format_text_sang_markdown, tim_dong_lap, xoa_dong_lap
from normalization.common_fix import hau_xu_ly_loi_chung
from normalization.rare_fix import hau_xu_ly_loi_rieng
from processing.text_layer_quality import is_bad_pdf_text_layer
from normalization.ctu_terms import hau_xu_ly_tu_dien_ctu
from processing.table_form_postprocess import postprocess_final_markdown
from processing.page_markers import page_marker
from validation.apply_metadata import ap_dung_va_xac_thuc_metadata

from cli_args import (
    cau_hinh_tu_args,
    la_output_file_md,
    tao_output_path,
    tao_parser,
    tim_file_cli,
)


# =========================================================
# HẬU XỬ LÝ 3 LỚP
# =========================================================


def chay_ba_lop_hau_xu_ly(text: str, cau_hinh: CauHinhOCR) -> str:
    """Chạy 3 lớp hậu xử lý: lỗi chung -> từ điển CTU -> lỗi riêng."""
    text = lam_sach_text(text)
    if cau_hinh.dung_loi_chung:
        text = hau_xu_ly_loi_chung(text)
    if cau_hinh.dung_tu_dien_ctu:
        text = hau_xu_ly_tu_dien_ctu(text)
    if cau_hinh.dung_loi_rieng:
        text = hau_xu_ly_loi_rieng(text, cau_hinh)
    return lam_sach_text(text)


# =========================================================
# RENDER PDF / OCR TRANG
# =========================================================


def render_trang_pdf(page: fitz.Page, file_stem: str, page_number: int, cau_hinh: CauHinhOCR) -> str | None:
    """Render một trang PDF thành ảnh PNG, có cache để không render lại."""
    image_path = os.path.join(cau_hinh.thu_muc_anh_tam, f"{ten_file_an_toan(file_stem)}_page_{page_number}.png")
    if cau_hinh.dung_cache_anh and os.path.exists(image_path):
        print(f"[CACHE] Dùng lại ảnh trang đã có: {image_path}")
        return image_path
    if cau_hinh.chi_dung_anh_cache:
        print(f"[SKIP] Chưa có ảnh cache trang {page_number}, bỏ qua render.")
        return None

    print(f"[RENDER] Trang {page_number} -> ảnh, dpi={cau_hinh.dpi}")
    try:
        pix = page.get_pixmap(dpi=cau_hinh.dpi, alpha=False)
    except TypeError:
        pix = page.get_pixmap(dpi=cau_hinh.dpi)
    Path(image_path).parent.mkdir(parents=True, exist_ok=True)
    pix.save(image_path)
    return image_path


def ocr_anh(image_path: str, cau_hinh: CauHinhOCR) -> tuple[str, str]:
    """OCR ảnh bằng Paddle+VietOCR; import lazy để không cần khởi động OCR engine
    khi chỉ xử lý PDF text copy."""
    from engines.ocr_engine import ocr_anh_bang_paddle_vietocr, ocr_anh_paddle_thuan

    text = ocr_anh_bang_paddle_vietocr(image_path, cau_hinh)
    method = "paddle_detect_vietocr_recognize"
    if not text:
        text = ocr_anh_paddle_thuan(image_path, cau_hinh)
        method = "paddleocr_plain"
    return chay_ba_lop_hau_xu_ly(text, cau_hinh), method


def xu_ly_trang_pdf_text(page: fitz.Page, raw_text: str, cau_hinh: CauHinhOCR) -> tuple[str, int, int]:
    """Xử lý trang PDF có text layer (TableSafe: không dùng PyMuPDF find_tables)."""
    parts = ["<!-- extraction: pymupdf_text_no_table -->"]
    text = chay_ba_lop_hau_xu_ly(raw_text, cau_hinh)
    text_md = format_text_sang_markdown(text, cau_hinh)
    if text_md:
        parts.append(text_md)
    return "\n\n".join(parts), len(text), 0


def xu_ly_trang_pdf_scan(page: fitz.Page, file_stem: str, page_number: int, cau_hinh: CauHinhOCR) -> tuple[str, int, int]:
    """Xử lý trang PDF scan: render sang ảnh rồi OCR."""
    image_path = render_trang_pdf(page, file_stem, page_number, cau_hinh)
    parts = ["<!-- extraction: ocr_pdf_scan -->"]
    if image_path is None:
        parts.append("[Không có ảnh cache để OCR trang này]")
        return "\n\n".join(parts), 0, 0

    text, method = ocr_anh(image_path, cau_hinh)
    parts.append(f"<!-- ocr_method: {method} -->")
    if text:
        parts.append(format_text_sang_markdown(text, cau_hinh))
        return "\n\n".join(parts), len(text), 0
    parts.append("[Trang này không OCR được text]")
    return "\n\n".join(parts), 0, 0


# =========================================================
# XỬ LÝ FILE
# =========================================================


def tinh_khoang_trang(total_pages: int, cau_hinh: CauHinhOCR) -> tuple[int, int]:
    """Tính khoảng trang cần xử lý theo cấu hình, đánh số bắt đầu từ 1."""
    start = max(1, int(cau_hinh.trang_bat_dau or 1))
    end = int(cau_hinh.trang_ket_thuc or 0)
    if end <= 0 or end > total_pages:
        end = total_pages
    if start > total_pages:
        start = total_pages
    if end < start:
        end = start
    return start, end


def xu_ly_pdf(pdf_path: str | Path, cau_hinh: CauHinhOCR) -> tuple[str, dict[str, int]]:
    """Xử lý PDF hybrid: tự chọn PyMuPDF text hoặc OCR theo từng trang."""
    print("3. Bắt đầu xử lý PDF")
    doc = fitz.open(pdf_path)
    file_stem = Path(pdf_path).stem
    total_pages = len(doc)

    raw_page_texts: list[str] = []
    for page_index, page in enumerate(doc):
        page_number = page_index + 1
        raw_text = lam_sach_text(page.get_text("text"))

        if cau_hinh.bo_qua_text_layer_pdf:
            if raw_text:
                print(f"[OCR] Trang {page_number} -> --force-ocr, bỏ qua text layer PDF")
            raw_page_texts.append("")
            continue

        if cau_hinh.tu_dong_bo_text_layer_loi and raw_text and is_bad_pdf_text_layer(raw_text):
            print(f"[OCR] Trang {page_number} -> text layer lỗi, OCR lại từ ảnh scan")
            raw_page_texts.append("")
            continue

        raw_page_texts.append(raw_text)

    repeated_lines = set()
    if cau_hinh.xoa_header_footer_lap:
        repeated_lines = tim_dong_lap(raw_page_texts, min_ratio=cau_hinh.ti_le_lap_header_footer)

    start_page, end_page = tinh_khoang_trang(total_pages, cau_hinh)
    if start_page != 1 or end_page != total_pages:
        print(f"[INFO] Chỉ xử lý trang {start_page} đến {end_page} / {total_pages} trang")

    pages_md: list[str] = []
    total_chars = pymupdf_pages = ocr_pages = table_pages = 0

    for page_index in range(start_page - 1, end_page):
        page = doc[page_index]
        page_number = page_index + 1
        raw_text = xoa_dong_lap(raw_page_texts[page_index], repeated_lines)
        raw_text = chay_ba_lop_hau_xu_ly(raw_text, cau_hinh)

        page_parts = [page_marker(page_number)]
        if len(raw_text) >= cau_hinh.do_dai_text_toi_thieu:
            pymupdf_pages += 1
            content, chars, tables = xu_ly_trang_pdf_text(page, raw_text, cau_hinh)
        else:
            ocr_pages += 1
            content, chars, tables = xu_ly_trang_pdf_scan(page, file_stem, page_number, cau_hinh)
        total_chars += chars
        table_pages += tables
        page_parts.extend([content, "\n---\n"])
        pages_md.append("\n\n".join(page_parts))

    doc.close()
    metadata = {
        "total_pages": end_page - start_page + 1,
        "total_characters": total_chars,
        "pymupdf_pages": pymupdf_pages,
        "ocr_pages": ocr_pages,
        "table_pages": table_pages,
        "source_total_pages": total_pages,
        "page_start": start_page,
        "page_end": end_page,
    }
    return "\n\n".join(pages_md), metadata


def xu_ly_file_anh(image_path: str | Path, cau_hinh: CauHinhOCR) -> tuple[str, dict[str, int]]:
    """Xử lý một file ảnh đơn lẻ và xuất Markdown."""
    text, method = ocr_anh(str(image_path), cau_hinh)
    parts = [page_marker(1), f"<!-- extraction: {method} -->"]
    parts.append(format_text_sang_markdown(text, cau_hinh) if text else "[Ảnh này không OCR được text]")
    parts.append("\n---\n")
    metadata = {
        "total_pages": 1, "total_characters": len(text),
        "pymupdf_pages": 0, "ocr_pages": 1, "table_pages": 0,
        "source_total_pages": 1, "page_start": 1, "page_end": 1,
    }
    return "\n\n".join(parts), metadata


# =========================================================
# DISPATCH FILE THEO CLI
# =========================================================


def xu_ly_file_bang_cli(input_file: Path, args, force: bool = False) -> Path | None:
    """Xử lý một file theo CLI duy nhất.

    Luồng:
    - PDF  →  router TableSafe (engine auto-page/local/llamaparse)
    - Any  +  --engine llamaparse  →  run_document_parse
    - Image + engine local  →  local OCR
    - Định dạng khác + local  →  thông báo không hỗ trợ
    """
    output_path = tao_output_path(input_file, args.output)

    if output_path.exists() and not force:
        print(f"[SKIP] Output đã tồn tại: {output_path}")
        return output_path

    cau_hinh = cau_hinh_tu_args(args, output_dir=output_path.parent)
    tao_thu_muc_can_thiet(cau_hinh)
    ext = input_file.suffix.lower()

    # PDF → router TableSafe (xử lý engine nội bộ)
    if ext == ".pdf":
        from pipeline.hybrid_page_router import run_table_safe_pdf
        print(f"[PROCESS] PDF TableSafe: {input_file}")
        return run_table_safe_pdf(
            input_path=input_file, output_path=output_path,
            engine=args.engine, page_start=args.page_start or None,
            page_end=args.page_end or None, manual_table_pages=args.table_pages,
            llama_tier=args.llama_tier, export_tables_as_xlsx=args.xlsx,
            preserve_spatial_text=args.spatial, disable_cache=args.disable_cache,
            aggressive_tables=args.aggressive_tables,
            repair_false_tables=not args.no_repair_false_tables,
            base_config=cau_hinh,
        )

    # Mọi định dạng khi engine=llamaparse → run_document_parse
    if args.engine == "llamaparse":
        from pipeline.hybrid_router import run_document_parse
        print(f"[PROCESS] LlamaParse: {input_file}")
        return run_document_parse(
            input_path=input_file, output_path=output_path, engine="llamaparse",
            page_start=args.page_start or None, page_end=args.page_end or None,
            llama_tier=args.llama_tier, export_tables_as_xlsx=args.xlsx,
            preserve_spatial_text=args.spatial, disable_cache=args.disable_cache,
            aggressive_tables=args.aggressive_tables,
            repair_false_tables=not args.no_repair_false_tables,
        )

    # Ảnh với engine local
    if ext in DUOI_ANH:
        print(f"[PROCESS] Image local OCR: {input_file}")
        body, _ = xu_ly_file_anh(input_file, cau_hinh)
        final_md = postprocess_final_markdown(body)
        final_md = ap_dung_va_xac_thuc_metadata(final_md, output_path, input_file, cau_hinh.ngon_ngu_ocr)
        ghi_text_unicode(output_path, final_md)
        return output_path

    print(f"[SKIP] Định dạng {input_file.suffix!r} chưa hỗ trợ local. Dùng --engine llamaparse.")
    return None


# =========================================================
# ENTRY POINT
# =========================================================


def main() -> None:
    args = tao_parser().parse_args()
    files = tim_file_cli(args.path, args.engine)
    if not files:
        print(f"[WARN] Không tìm thấy file hỗ trợ trong: {args.path}")
        return

    if len(files) > 1 and la_output_file_md(args.output):
        print("[ERROR] Khi input là thư mục/nhiều file, --output phải là thư mục, không phải file .md")
        return

    print(f"[INFO] Tìm thấy {len(files)} file cần xử lý")
    for file_path in files:
        try:
            out = xu_ly_file_bang_cli(file_path, args, force=args.force)
            if out:
                print(f"[OK] Đã tạo Markdown: {Path(out).resolve()}")
        except Exception as exc:
            print(f"[ERROR] Lỗi khi xử lý {file_path}: {exc}")


if __name__ == "__main__":
    main()
