"""
cli_args.py
Toàn bộ logic dòng lệnh được tách ra khỏi main.py để giữ main ngắn gọn:
  - Xây dựng argparse parser (chia thành 4 nhóm arg)
  - Chuyển args → CauHinhOCR
  - Xác định output path và tìm file input

main.py chỉ còn chứa logic xử lý OCR và dispatch.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from config import (
    CAU_HINH_MAC_DINH,
    DUOI_ANH,
    DUOI_PDF,
    CauHinhOCR,
    cau_hinh_cho_thu_muc,
)


# =========================================================
# ARGUMENT GROUPS
# =========================================================


def _add_routing_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("Page range / routing")
    g.add_argument("--page-start", type=int, default=0, help="Trang bắt đầu, đánh số từ 1. 0 = từ đầu.")
    g.add_argument("--page-end", type=int, default=0, help="Trang kết thúc, đánh số từ 1. 0 = đến cuối.")
    g.add_argument(
        "--table-pages",
        default=None,
        help="Chỉ định thủ công trang dùng LlamaParse, ví dụ: 4,6,8-10. Bỏ trống thì auto detect.",
    )


def _add_llama_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("LlamaParse options")
    g.add_argument(
        "--llama-tier",
        choices=["fast", "cost_effective", "agentic", "agentic_plus"],
        default="agentic",
        help="Tier LlamaParse cho trang bảng/lưu đồ hoặc khi --engine llamaparse.",
    )
    g.add_argument("--xlsx", action="store_true", help="Yêu cầu LlamaParse xuất metadata bảng dạng XLSX.")
    g.add_argument("--spatial", action="store_true", help="Bật spatial text cho bảng/form/layout khó.")
    g.add_argument("--disable-cache", action="store_true", help="Không dùng cache của LlamaParse.")
    g.add_argument(
        "--aggressive-tables",
        action="store_true",
        help="Bật aggressive table extraction. Chỉ dùng khi trang thật sự có bảng/lưu đồ phức tạp.",
    )
    g.add_argument("--no-repair-false-tables", action="store_true", help="Tắt hậu xử lý sửa bảng giả của LlamaParse.")


def _add_local_ocr_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("Local OCR options")
    g.add_argument(
        "--force-ocr",
        action="store_true",
        help="Bỏ qua text layer PDF và OCR lại từ ảnh scan.",
    )
    g.add_argument(
        "--no-auto-bad-text-layer-check",
        action="store_true",
        help="Tắt tự động phát hiện text layer OCR cũ bị lỗi.",
    )
    g.add_argument("--dpi", type=int, default=CAU_HINH_MAC_DINH.dpi, help="DPI render PDF scan.")
    g.add_argument("--lang", default=CAU_HINH_MAC_DINH.ngon_ngu_ocr, help="Ngôn ngữ PaddleOCR: vi, latin, en.")
    g.add_argument("--gpu", action="store_true", help="Bật GPU nếu đã cài Paddle GPU/Torch GPU.")
    g.add_argument("--no-vietocr", action="store_true", help="Tắt VietOCR, dùng PaddleOCR thuần.")
    g.add_argument(
        "--vietocr-model",
        default=CAU_HINH_MAC_DINH.vietocr_model,
        choices=["vgg_transformer", "vgg_seq2seq"],
        help="Model VietOCR.",
    )
    g.add_argument("--vietocr-weights", default="", help="Đường dẫn weights VietOCR custom nếu có.")
    g.add_argument("--crop-padding", type=int, default=CAU_HINH_MAC_DINH.padding_crop, help="Padding quanh crop OCR.")
    g.add_argument("--save-crops", action="store_true", help="Lưu crop VietOCR để debug.")
    g.add_argument("--no-image-cache", action="store_true", help="Không dùng cache ảnh render/tiền xử lý.")
    g.add_argument("--existing-images-only", action="store_true", help="Chỉ dùng ảnh cache đã có, không render trang mới.")
    g.add_argument("--no-red-stamp-clean", action="store_true", help="Không xóa con dấu đỏ trước OCR.")
    g.add_argument("--no-symbol-fallback", action="store_true", help="Không fallback PaddleOCR cho dòng nghi ký tự đặc biệt.")
    g.add_argument(
        "--layout-merge-mode",
        default="conservative",
        choices=["conservative", "aggressive"],
        help="Chế độ gộp dòng.",
    )


def _add_postprocess_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("Normalization layers")
    g.add_argument("--loi-rieng-json", default="", help="File JSON chứa rule sửa lỗi riêng ngoài source.")
    g.add_argument("--no-loi-chung", action="store_true", help="Tắt lớp 1 xử lý lỗi chung.")
    g.add_argument("--no-tu-dien-ctu", action="store_true", help="Tắt lớp 2 từ điển CTU.")
    g.add_argument("--no-loi-rieng", action="store_true", help="Tắt lớp 3 lỗi riêng/review.")
    g.add_argument("--no-debug-images", action="store_true", help="Không giữ ảnh biến thể debug.")


# =========================================================
# PARSER CHÍNH
# =========================================================


def tao_parser() -> argparse.ArgumentParser:
    """Tạo parser dòng lệnh duy nhất cho toàn bộ pipeline.

    Engine:
    - auto-page: khuyến nghị cho PDF; trang văn bản thường dùng local,
                 trang bảng/lưu đồ dùng LlamaParse.
    - local: chạy hoàn toàn local, không gọi LlamaParse.
    - llamaparse: dùng LlamaParse cho toàn bộ file/trang được chọn.
    """
    p = argparse.ArgumentParser(
        description=(
            "OCR CTU TableSafe: một main duy nhất. "
            "Local PyMuPDF text/Paddle+VietOCR cho trang thường, "
            "LlamaParse cho trang bảng/lưu đồ."
        )
    )
    p.add_argument("path", help="Đường dẫn file PDF/ảnh hoặc thư mục input.")
    p.add_argument(
        "--engine",
        choices=["auto-page", "local", "llamaparse"],
        default="auto-page",
        help="auto-page: tự route từng trang PDF; local: không dùng LlamaParse; llamaparse: dùng LlamaParse toàn bộ.",
    )
    p.add_argument(
        "-o", "--output",
        default=CAU_HINH_MAC_DINH.thu_muc_output,
        help="Thư mục lưu output, hoặc file .md cụ thể khi input là 1 file.",
    )
    p.add_argument("--force", action="store_true", help="Xử lý lại dù output đã tồn tại.")
    _add_routing_args(p)
    _add_llama_args(p)
    _add_local_ocr_args(p)
    _add_postprocess_args(p)
    return p


# =========================================================
# CHUYỂN ARGS → CONFIG
# =========================================================


def cau_hinh_tu_args(args: argparse.Namespace, output_dir: str | Path | None = None) -> CauHinhOCR:
    """Chuyển argparse Namespace thành CauHinhOCR."""
    return cau_hinh_cho_thu_muc(
        Path(output_dir or args.output),
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


# =========================================================
# PATH HELPERS
# =========================================================


def la_output_file_md(output_value: str | Path) -> bool:
    """Kiểm tra --output có phải đường dẫn file Markdown hay không."""
    return Path(output_value).suffix.lower() == ".md"


def tao_output_path(input_file: Path, output_value: str | Path) -> Path:
    """Tạo output path cho một file input.

    Nếu --output là file .md thì dùng đúng file đó.
    Nếu là thư mục thì tạo <output>/<ten_file>_structured.md.
    """
    from config import ten_file_an_toan

    out = Path(output_value)
    if la_output_file_md(out):
        return out
    return out / f"{ten_file_an_toan(input_file.stem)}_structured.md"


def tim_file_cli(path: str | Path, engine: str) -> list[Path]:
    """Tìm file phù hợp cho CLI.

    Local hỗ trợ PDF/ảnh. LlamaParse thêm DOCX/PPTX/XLSX/CSV/HTML.
    """
    p = Path(path)
    allowed = set(DUOI_PDF) | set(DUOI_ANH)
    if engine == "llamaparse":
        allowed |= {".docx", ".pptx", ".xlsx", ".csv", ".html"}

    if p.is_file():
        return [p] if p.suffix.lower() in allowed else []

    return sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in allowed) if p.is_dir() else []
