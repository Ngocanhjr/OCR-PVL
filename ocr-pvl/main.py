"""
chay_ocr.py
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
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import fitz  # PyMuPDF

from config import (
    CAU_HINH_MAC_DINH,
    DUOI_ANH,
    DUOI_PDF,
    CauHinhOCR,
    ghi_text_unicode,
    lam_sach_text,
    tao_thu_muc_can_thiet,
    ten_file_an_toan,
)
from processing.markdown_layout import format_text_sang_markdown, tim_dong_lap, xoa_dong_lap
from normalization.common_fix import hau_xu_ly_loi_chung
from normalization.rare_fix import ghi_bao_cao_review, hau_xu_ly_loi_rieng, tao_bao_cao_review
from processing.text_layer_quality import is_bad_pdf_text_layer
from normalization.ctu_terms import canh_bao_thuat_ngu_ctu, hau_xu_ly_tu_dien_ctu
from processing.table_form_postprocess import postprocess_final_markdown
from processing.page_markers import page_marker
from validation.apply_metadata import apply_metadata_to_markdown
from validation.validate_metadata import validate_metadata_text


# =========================================================
# HẬU XỬ LÝ 3 LỚP
# =========================================================


def chay_ba_lop_hau_xu_ly(text: str, cau_hinh: CauHinhOCR) -> str:
    """Chạy 3 lớp hậu xử lý theo đúng thứ tự: lỗi chung -> từ điển CTU -> lỗi riêng."""

    text = lam_sach_text(text)
    if cau_hinh.dung_loi_chung:
        text = hau_xu_ly_loi_chung(text)
    if cau_hinh.dung_tu_dien_ctu:
        text = hau_xu_ly_tu_dien_ctu(text)
    if cau_hinh.dung_loi_rieng:
        text = hau_xu_ly_loi_rieng(text, cau_hinh)
    return lam_sach_text(text)


# =========================================================
# GHI CHÚ VỀ BẢNG
# =========================================================

# Bản TableSafe KHÔNG trích bảng bằng PyMuPDF.
# Lý do: PyMuPDF find_tables() dễ biến đoạn văn bản thường thành bảng giả
# trong tài liệu hành chính có nhiều dòng thẳng hàng.
# Nếu trang thật sự có bảng/lưu đồ, hãy dùng main.py --engine auto-page để router
# tự gọi LlamaParse cho riêng các trang đó.


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
    """OCR ảnh bằng Paddle+VietOCR; import OCR engine theo kiểu lazy.

    Nhờ lazy import, PDF text copy được vẫn chạy được mà không cần khởi tạo
    PaddleOCR/VietOCR. Chỉ khi thật sự gặp ảnh hoặc PDF scan mới cần các thư viện OCR nặng.
    """

    from engines.ocr_engine import ocr_anh_bang_paddle_vietocr, ocr_anh_paddle_thuan

    text = ocr_anh_bang_paddle_vietocr(image_path, cau_hinh)
    method = "paddle_detect_vietocr_recognize"
    if not text:
        text = ocr_anh_paddle_thuan(image_path, cau_hinh)
        method = "paddleocr_plain"
    text = chay_ba_lop_hau_xu_ly(text, cau_hinh)
    return text, method


def xu_ly_trang_pdf_text(page: fitz.Page, raw_text: str, cau_hinh: CauHinhOCR) -> tuple[str, int, int]:
    """Xử lý trang PDF có text layer mà KHÔNG trích bảng bằng PyMuPDF.

    Bản TableSafe chỉ lấy text thật của trang, sau đó gộp dòng và định dạng
    Markdown. Không gọi page.find_tables() để tránh tạo bảng giả ở các trang
    văn bản thường. Nếu cần bảng thật, dùng `main.py --engine auto-page` để LlamaParse
    xử lý riêng trang có bảng/lưu đồ.
    """

    parts = ["<!-- extraction: pymupdf_text_no_table -->"]
    text = chay_ba_lop_hau_xu_ly(raw_text, cau_hinh)
    text_md = format_text_sang_markdown(text, cau_hinh)
    if text_md:
        parts.append(text_md)
    return "\n\n".join(parts), len(text), 0


def xu_ly_trang_pdf_scan(page: fitz.Page, file_stem: str, page_number: int, cau_hinh: CauHinhOCR) -> tuple[str, int, int]:
    """Xử lý một trang PDF scan: render sang ảnh rồi OCR."""

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
    """Tính khoảng trang cần xử lý theo cấu hình, đánh số trang bắt đầu từ 1."""

    start_page = int(cau_hinh.trang_bat_dau or 0)
    end_page = int(cau_hinh.trang_ket_thuc or 0)
    if start_page <= 0:
        start_page = 1
    if end_page <= 0 or end_page > total_pages:
        end_page = total_pages
    if start_page > total_pages:
        start_page = total_pages
    if end_page < start_page:
        end_page = start_page
    return start_page, end_page


def xu_ly_pdf(pdf_path: str | Path, cau_hinh: CauHinhOCR) -> tuple[str, dict[str, int]]:
    """Xử lý PDF hybrid: tự chọn PyMuPDF text hoặc OCR theo từng trang."""

    print("3. Bắt đầu xử lý PDF")
    doc = fitz.open(pdf_path)
    file_stem = Path(pdf_path).stem
    total_pages = len(doc)

    # Không phải PDF nào có page.get_text("text") cũng là PDF text thật.
    # Nhiều PDF scan có text layer OCR cũ bị hỏng, ví dụ: "BQ GIAO Dl)C",
    # "TRUONGD~IHQccANTHa", "DQc l~p", "QUYETDJNH".
    # Với các trang như vậy phải bỏ text layer và OCR lại từ ảnh scan.
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
    total_chars = 0
    pymupdf_pages = 0
    ocr_pages = 0
    table_pages = 0

    for page_index in range(start_page - 1, end_page):
        page = doc[page_index]
        page_number = page_index + 1
        raw_text = xoa_dong_lap(raw_page_texts[page_index], repeated_lines)
        raw_text = chay_ba_lop_hau_xu_ly(raw_text, cau_hinh)

        page_parts = [page_marker(page_number)]
        if len(raw_text) >= cau_hinh.do_dai_text_toi_thieu:
            pymupdf_pages += 1
            content, chars, tables = xu_ly_trang_pdf_text(page, raw_text, cau_hinh)
            total_chars += chars
            table_pages += tables
        else:
            ocr_pages += 1
            content, chars, tables = xu_ly_trang_pdf_scan(page, file_stem, page_number, cau_hinh)
            total_chars += chars
            table_pages += tables
        page_parts.append(content)
        page_parts.append("\n---\n")
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
        "total_pages": 1,
        "total_characters": len(text),
        "pymupdf_pages": 0,
        "ocr_pages": 1,
        "table_pages": 0,
        "source_total_pages": 1,
        "page_start": 1,
        "page_end": 1,
    }
    return "\n\n".join(parts), metadata




def gan_yaml_metadata_chuan(final_md: str, output_path: str | Path, source_path: str | Path, cau_hinh: CauHinhOCR) -> str:
    """Gắn YAML front matter chuẩn cho output OCR trước khi ghi Markdown."""

    final_md = apply_metadata_to_markdown(
        final_md,
        md_path=output_path,
        source_file=source_path,
        language=cau_hinh.ngon_ngu_ocr,
    )
    errors, warnings = validate_metadata_text(final_md)
    for error in errors:
        print(f"[METADATA ERROR] {output_path}: {error}")
    for warning in warnings:
        print(f"[METADATA WARN] {output_path}: {warning}")
    return final_md





# =========================================================
# CLI DUY NHẤT
# =========================================================


def tao_parser() -> argparse.ArgumentParser:
    """Tạo bộ đọc tham số dòng lệnh duy nhất cho toàn bộ pipeline.

    Chỉ còn một file chạy chính là `main.py`.

    Engine:
    - auto-page: khuyến nghị cho PDF; trang văn bản thường dùng local, trang bảng/lưu đồ dùng LlamaParse.
    - local: chạy hoàn toàn local, không gọi LlamaParse và không tạo bảng bằng PyMuPDF.
    - llamaparse: dùng LlamaParse cho toàn bộ file/trang được chọn.
    """

    parser = argparse.ArgumentParser(
        description=(
            "OCR CTU TableSafe: một main duy nhất. "
            "Local PyMuPDF text/Paddle+VietOCR cho trang thường, "
            "LlamaParse cho trang bảng/lưu đồ."
        )
    )
    parser.add_argument("path", help="Đường dẫn file PDF/ảnh hoặc thư mục input.")
    parser.add_argument(
        "--engine",
        choices=["auto-page", "local", "llamaparse"],
        default="auto-page",
        help=(
            "auto-page: tự route từng trang PDF; "
            "local: không dùng LlamaParse; "
            "llamaparse: dùng LlamaParse toàn bộ file/trang."
        ),
    )
    parser.add_argument(
        "-o", "--output",
        default=CAU_HINH_MAC_DINH.thu_muc_output,
        help=(
            "Nếu là thư mục: thư mục lưu output. "
            "Nếu là file .md và input là 1 file: ghi đúng file .md đó."
        ),
    )
    parser.add_argument("--force", action="store_true", help="Xử lý lại dù output đã tồn tại.")

    # Page range / routing
    parser.add_argument("--page-start", type=int, default=0, help="Trang bắt đầu, đánh số từ 1. 0 = từ đầu.")
    parser.add_argument("--page-end", type=int, default=0, help="Trang kết thúc, đánh số từ 1. 0 = đến cuối.")
    parser.add_argument(
        "--table-pages",
        default=None,
        help="Chỉ định thủ công trang dùng LlamaParse, ví dụ: 4,6,8-10. Bỏ trống thì auto detect.",
    )

    # LlamaParse options
    parser.add_argument(
        "--llama-tier",
        choices=["fast", "cost_effective", "agentic", "agentic_plus"],
        default="agentic",
        help="Tier LlamaParse cho trang bảng/lưu đồ hoặc khi --engine llamaparse.",
    )
    parser.add_argument("--xlsx", action="store_true", help="Yêu cầu LlamaParse xuất metadata bảng dạng XLSX nếu SDK hỗ trợ.")
    parser.add_argument("--spatial", action="store_true", help="Bật spatial text cho bảng/form/layout khó.")
    parser.add_argument("--disable-cache", action="store_true", help="Không dùng cache của LlamaParse.")
    parser.add_argument(
        "--aggressive-tables",
        action="store_true",
        help="Bật aggressive table extraction của LlamaParse. Chỉ dùng khi trang thật sự có bảng/lưu đồ phức tạp.",
    )
    parser.add_argument("--no-repair-false-tables", action="store_true", help="Tắt hậu xử lý sửa bảng giả của LlamaParse.")

    # Local OCR options
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Bỏ qua text layer PDF và OCR lại từ ảnh scan. Dùng khi text layer PDF bị lỗi.",
    )
    parser.add_argument(
        "--no-auto-bad-text-layer-check",
        action="store_true",
        help="Tắt tự động phát hiện text layer OCR cũ bị lỗi. Mặc định đang bật.",
    )
    parser.add_argument("--dpi", type=int, default=CAU_HINH_MAC_DINH.dpi, help="DPI render PDF scan.")
    parser.add_argument("--lang", default=CAU_HINH_MAC_DINH.ngon_ngu_ocr, help="Ngôn ngữ PaddleOCR: vi, latin, en.")
    parser.add_argument("--gpu", action="store_true", help="Bật GPU nếu đã cài Paddle GPU/Torch GPU.")
    parser.add_argument("--no-vietocr", action="store_true", help="Tắt VietOCR, dùng PaddleOCR thuần.")
    parser.add_argument(
        "--vietocr-model",
        default=CAU_HINH_MAC_DINH.vietocr_model,
        choices=["vgg_transformer", "vgg_seq2seq"],
        help="Model VietOCR.",
    )
    parser.add_argument("--vietocr-weights", default="", help="Đường dẫn weights VietOCR custom nếu có.")
    parser.add_argument("--crop-padding", type=int, default=CAU_HINH_MAC_DINH.padding_crop, help="Padding quanh crop OCR.")
    parser.add_argument("--save-crops", action="store_true", help="Lưu crop VietOCR để debug.")
    parser.add_argument("--no-image-cache", action="store_true", help="Không dùng cache ảnh render/ảnh tiền xử lý.")
    parser.add_argument("--existing-images-only", action="store_true", help="Chỉ dùng ảnh cache đã có, không render trang mới.")
    parser.add_argument("--no-red-stamp-clean", action="store_true", help="Không xóa con dấu đỏ trước OCR.")
    parser.add_argument("--no-symbol-fallback", action="store_true", help="Không fallback PaddleOCR cho dòng nghi ký tự đặc biệt.")
    parser.add_argument(
        "--layout-merge-mode",
        default="conservative",
        choices=["conservative", "aggressive"],
        help="Chế độ gộp dòng.",
    )
    parser.add_argument("--loi-rieng-json", default="", help="File JSON chứa rule sửa lỗi riêng nếu muốn auto-fix ngoài source.")
    parser.add_argument("--no-loi-chung", action="store_true", help="Tắt lớp 1 xử lý lỗi chung.")
    parser.add_argument("--no-tu-dien-ctu", action="store_true", help="Tắt lớp 2 từ điển CTU.")
    parser.add_argument("--no-loi-rieng", action="store_true", help="Tắt lớp 3 lỗi riêng/review.")
    parser.add_argument("--no-debug-images", action="store_true", help="Không giữ ảnh biến thể debug.")
    return parser


def cau_hinh_tu_args(args: argparse.Namespace, output_dir: str | Path | None = None) -> CauHinhOCR:
    """Chuyển argparse Namespace thành CauHinhOCR.

    `output_dir` cho phép wrapper truyền thư mục output khi người dùng nhập `-o file.md`.
    """

    out_dir = str(output_dir or args.output)
    return CauHinhOCR(
        thu_muc_output=out_dir,
        thu_muc_anh_tam=os.path.join(out_dir, "temp_images"),
        thu_muc_bao_cao=os.path.join(out_dir, "review_reports"),
        dpi=args.dpi,
        trang_bat_dau=args.page_start,
        trang_ket_thuc=args.page_end,
        bo_qua_text_layer_pdf=args.force_ocr,
        tu_dong_bo_text_layer_loi=not args.no_auto_bad_text_layer_check,
        ngon_ngu_ocr=args.lang,
        dung_gpu=args.gpu,
        dung_vietocr=not args.no_vietocr,
        vietocr_model=args.vietocr_model,
        vietocr_weights=args.vietocr_weights,
        padding_crop=args.crop_padding,
        dung_cache_anh=not args.no_image_cache,
        chi_dung_anh_cache=args.existing_images_only,
        luu_anh_debug=not args.no_debug_images,
        luu_crop_vietocr=args.save_crops,
        xoa_con_dau_do=not args.no_red_stamp_clean,
        fallback_ky_tu_dac_biet=not args.no_symbol_fallback,
        dung_loi_chung=not args.no_loi_chung,
        dung_tu_dien_ctu=not args.no_tu_dien_ctu,
        dung_loi_rieng=not args.no_loi_rieng,
        file_loi_rieng_json=args.loi_rieng_json,
        che_do_gop_dong=args.layout_merge_mode,
    )


def la_output_file_md(output_value: str | Path) -> bool:
    """Kiểm tra `--output` có phải đường dẫn file Markdown hay không."""
    return Path(output_value).suffix.lower() == ".md"


def tao_output_path(input_file: Path, output_value: str | Path) -> Path:
    """Tạo output path cho một file input.

    Nếu `--output` là file .md thì dùng đúng file đó. Nếu là thư mục thì tạo
    `<output>/<ten_file>_structured.md`.
    """
    out = Path(output_value)
    if la_output_file_md(out):
        return out
    return out / f"{ten_file_an_toan(input_file.stem)}_structured.md"


def xu_ly_file_bang_cli(input_file: Path, args: argparse.Namespace, force: bool = False) -> Path | None:
    """Xử lý một file theo CLI duy nhất.

    PDF sẽ dùng router TableSafe để tránh bảng giả PyMuPDF. Ảnh dùng local OCR.
    Các định dạng DOCX/PPTX/XLSX chỉ chạy được khi `--engine llamaparse` vì local
    PadViet hiện chỉ hỗ trợ PDF/ảnh.
    """
    output_path = tao_output_path(input_file, args.output)
    output_dir = output_path.parent

    if output_path.exists() and not force:
        print(f"[SKIP] Output đã tồn tại: {output_path}")
        return output_path

    cau_hinh = cau_hinh_tu_args(args, output_dir=output_dir)
    tao_thu_muc_can_thiet(cau_hinh)

    ext = input_file.suffix.lower()
    if ext == ".pdf":
        # Import lazy để tránh vòng import khi hybrid_page_router cần gọi lại main.xu_ly_pdf.
        from pipeline.hybrid_page_router import run_table_safe_pdf

        print(f"[PROCESS] PDF TableSafe: {input_file}")
        return run_table_safe_pdf(
            input_path=input_file,
            output_path=output_path,
            engine=args.engine,
            page_start=args.page_start or None,
            page_end=args.page_end or None,
            manual_table_pages=args.table_pages,
            llama_tier=args.llama_tier,
            export_tables_as_xlsx=args.xlsx,
            preserve_spatial_text=args.spatial,
            disable_cache=args.disable_cache,
            aggressive_tables=args.aggressive_tables,
            repair_false_tables=not args.no_repair_false_tables,
            base_config=cau_hinh,
        )

    if ext in DUOI_ANH:
        if args.engine == "llamaparse":
            from pipeline.hybrid_router import run_document_parse

            print(f"[PROCESS] Image bằng LlamaParse: {input_file}")
            return run_document_parse(
                input_path=input_file,
                output_path=output_path,
                engine="llamaparse",
                page_start=args.page_start or None,
                page_end=args.page_end or None,
                llama_tier=args.llama_tier,
                export_tables_as_xlsx=args.xlsx,
                preserve_spatial_text=args.spatial,
                disable_cache=args.disable_cache,
                aggressive_tables=args.aggressive_tables,
                repair_false_tables=not args.no_repair_false_tables,
            )

        print(f"[PROCESS] Image local OCR: {input_file}")
        body, _metadata = xu_ly_file_anh(input_file, cau_hinh)
        final_md = body
        final_md = postprocess_final_markdown(final_md)
        final_md = gan_yaml_metadata_chuan(final_md, output_path, input_file, cau_hinh)
        ghi_text_unicode(output_path, final_md)
        return output_path

    if args.engine == "llamaparse":
        from pipeline.hybrid_router import run_document_parse

        print(f"[PROCESS] Document bằng LlamaParse: {input_file}")
        return run_document_parse(
            input_path=input_file,
            output_path=output_path,
            engine="llamaparse",
            page_start=args.page_start or None,
            page_end=args.page_end or None,
            llama_tier=args.llama_tier,
            export_tables_as_xlsx=args.xlsx,
            preserve_spatial_text=args.spatial,
            disable_cache=args.disable_cache,
            aggressive_tables=args.aggressive_tables,
            repair_false_tables=not args.no_repair_false_tables,
        )

    print(f"[SKIP] Định dạng chưa hỗ trợ ở local: {input_file.suffix}. Muốn xử lý hãy dùng --engine llamaparse.")
    return None


def tim_file_cli(path: str | Path, engine: str) -> list[Path]:
    """Tìm file phù hợp cho CLI.

    Local hỗ trợ PDF/ảnh. LlamaParse có thể nhận thêm DOCX/PPTX/XLSX/CSV/HTML.
    """
    p = Path(path)
    extra_doc_exts = {".docx", ".pptx", ".xlsx", ".csv", ".html"}
    allowed = set(DUOI_PDF).union(DUOI_ANH)
    if engine == "llamaparse":
        allowed.update(extra_doc_exts)

    if p.is_file():
        return [p] if p.suffix.lower() in allowed else []

    files: list[Path] = []
    if p.is_dir():
        for item in sorted(p.rglob("*")):
            if item.is_file() and item.suffix.lower() in allowed:
                files.append(item)
    return files


def main() -> None:
    """Entry point duy nhất của source.

    Sau khi gộp, chỉ chạy:
        python main.py "file.pdf" --engine auto-page
    """

    args = tao_parser().parse_args()
    files = tim_file_cli(args.path, args.engine)
    if not files:
        print(f"[WARN] Không tìm thấy file hỗ trợ trong: {args.path}")
        return

    if len(files) > 1 and la_output_file_md(args.output):
        print("[ERROR] Khi input là thư mục/nhiều file, --output phải là thư mục, không được là file .md")
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
