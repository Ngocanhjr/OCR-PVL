"""
cau_hinh.py
Cấu hình chung và các hàm tiện ích nhỏ dùng toàn bộ pipeline OCR CTU.

Tên file dùng tiếng Việt không dấu để dễ hiểu chức năng và tránh lỗi đường dẫn.
"""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CauHinhOCR:
    """Lưu toàn bộ cấu hình chạy OCR.

    Các tham số được truyền giữa các module để tránh dùng quá nhiều biến global.
    Có thể đổi bằng tham số dòng lệnh trong `chay_ocr.py`.
    """

    thu_muc_output: str = "output"
    thu_muc_anh_tam: str = "output/temp_images"
    thu_muc_bao_cao: str = "output/review_reports"

    # PDF scan nên dùng 300 DPI để giữ ký tự nhỏ như @, -, “”, –.
    dpi: int = 300
    trang_bat_dau: int = 0
    trang_ket_thuc: int = 0
    do_dai_text_toi_thieu: int = 30

    # PDF scan có thể có text layer OCR cũ bị lỗi.
    # bo_qua_text_layer_pdf=True: ép OCR lại từ ảnh cho mọi trang PDF.
    # tu_dong_bo_text_layer_loi=True: tự phát hiện text layer hỏng và OCR lại từ ảnh.
    bo_qua_text_layer_pdf: bool = False
    tu_dong_bo_text_layer_loi: bool = True

    # OCR engine.
    ngon_ngu_ocr: str = "vi"
    dung_gpu: bool = False
    dung_vietocr: bool = True
    vietocr_model: str = "vgg_transformer"
    vietocr_weights: str = ""
    padding_crop: int = 8

    # Cache và debug.
    dung_cache_anh: bool = True
    chi_dung_anh_cache: bool = False
    luu_anh_debug: bool = True
    luu_crop_vietocr: bool = False

    # Tiền xử lý ảnh.
    xoa_con_dau_do: bool = True
    tao_bien_the_anh: bool = True

    # Fallback nhận dạng ký tự đặc biệt.
    fallback_ky_tu_dac_biet: bool = True

    # Lớp hậu xử lý.
    dung_loi_chung: bool = True
    dung_tu_dien_ctu: bool = True
    dung_loi_rieng: bool = True
    file_loi_rieng_json: str = ""

    # Layout.
    che_do_gop_dong: str = "conservative"  # conservative | aggressive
    xoa_header_footer_lap: bool = True
    ti_le_lap_header_footer: float = 0.60

    # PaddleOCR CPU ổn định hơn trên Windows yếu.
    bat_mkldnn: bool = False
    so_luong_cpu_threads: int = 1
    ocr_drop_score: float = 0.10
    det_db_thresh: float = 0.20
    det_db_box_thresh: float = 0.30
    det_db_unclip_ratio: float = 1.80


CAU_HINH_MAC_DINH = CauHinhOCR()
DUOI_PDF = {".pdf", ".doc", ".docx"}
DUOI_ANH = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def cau_hinh_cho_thu_muc(
    base: str | Path,
    nguon: "CauHinhOCR | None" = None,
    **overrides,
) -> "CauHinhOCR":
    """Tạo CauHinhOCR với ba đường dẫn derive từ base_dir.

    Dùng thay cho việc gọi dataclasses.replace() thủ công ở nhiều nơi:
        thu_muc_output = str(base)
        thu_muc_anh_tam = str(base / "temp_images")
        thu_muc_bao_cao = str(base / "review_reports")
    """
    from dataclasses import replace

    return replace(
        nguon or CAU_HINH_MAC_DINH,
        thu_muc_output=str(base),
        thu_muc_anh_tam=str(Path(base) / "temp_images"),
        thu_muc_bao_cao=str(Path(base) / "review_reports"),
        **overrides,
    )


def tao_thu_muc_can_thiet(cau_hinh: CauHinhOCR = CAU_HINH_MAC_DINH) -> None:
    """Tạo các thư mục output, ảnh tạm và báo cáo nếu chưa tồn tại."""

    os.makedirs(cau_hinh.thu_muc_output, exist_ok=True)
    os.makedirs(cau_hinh.thu_muc_anh_tam, exist_ok=True)
    os.makedirs(cau_hinh.thu_muc_bao_cao, exist_ok=True)


def ten_file_an_toan(ten: str, do_dai_toi_da: int = 120) -> str:
    """Chuẩn hóa tên file để lưu an toàn trên Windows/Linux/macOS."""

    stem = Path(str(ten)).stem
    stem = re.sub(r'[<>:"/\\|?*]+', "_", stem)
    stem = re.sub(r"\s+", "_", stem).strip("._ ")
    if len(stem) > do_dai_toi_da:
        digest = hashlib.md5(stem.encode("utf-8")).hexdigest()[:8]
        stem = stem[:do_dai_toi_da] + "_" + digest
    return stem or "untitled"


def tinh_checksum(path: str | Path) -> str:
    """Tính MD5 checksum để biết file nguồn có thay đổi hay không."""

    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def lam_sach_text(text: Any) -> str:
    """Làm sạch text nhiều dòng: bỏ null, chuẩn hóa xuống dòng và khoảng trắng."""

    if text is None:
        return ""
    text = str(text).replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def lam_sach_dong(line: Any) -> str:
    """Làm sạch một dòng: strip và gộp nhiều khoảng trắng thành một."""

    if line is None:
        return ""
    line = str(line).strip()
    line = re.sub(r"\s+", " ", line)
    return line


def iter_dong_sach(text: str):
    """Generator yield (lineno, line) cho từng dòng không trống sau lam_sach_dong.

    Dùng chung trong rare_fix, ctu_terms để tránh lặp pattern:
        for idx, raw in enumerate(text.splitlines(), start=1):
            line = lam_sach_dong(raw)
            if not line: continue
    """
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = lam_sach_dong(raw)
        if line:
            yield idx, line


def bo_dau_tieng_viet(text: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp từ khóa ít phụ thuộc lỗi dấu OCR."""

    text = str(text).replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", without_marks)


def chuan_hoa_de_so_khop(text: str, giu_khoang_trang: bool = True) -> str:
    """Chuẩn hóa text để match rule: bỏ dấu, lower, bỏ dấu câu dư."""

    text = bo_dau_tieng_viet(lam_sach_dong(text)).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not giu_khoang_trang:
        text = text.replace(" ", "")
    return text


def ghi_text_unicode(path: str | Path, noi_dung: str) -> None:
    """Ghi file text UTF-8 và tự tạo thư mục cha nếu cần."""

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(noi_dung)
