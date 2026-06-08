"""
tien_xu_ly_anh.py
Tiền xử lý ảnh OCR: đọc/ghi ảnh Unicode, xóa con dấu đỏ, tạo biến thể ảnh và crop box chữ.

Tái sử dụng ý tưởng tốt từ source cũ:
- Đọc/ghi ảnh bằng OpenCV + numpy.fromfile/tofile để hỗ trợ đường dẫn Unicode Windows.
- Xóa vùng đỏ của con dấu trước OCR để giảm nhiễu.
- Tạo ảnh cleaned/enhanced/upscaled/binary làm fallback.
- Crop box có padding để không mất ký tự nhỏ như @, -, “”, –.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from config import CauHinhOCR, CAU_HINH_MAC_DINH, ten_file_an_toan


def doc_anh_unicode(image_path: str):
    """Đọc ảnh bằng OpenCV, hỗ trợ đường dẫn Unicode trên Windows."""

    try:
        import cv2
        import numpy as np

        data = np.fromfile(image_path, dtype=np.uint8)
        if data.size == 0:
            return None
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None or img.size == 0:
            return None
        return img
    except Exception:
        return None


def ghi_anh_unicode(path: str, image) -> bool:
    """Ghi ảnh bằng OpenCV, hỗ trợ đường dẫn Unicode trên Windows."""

    try:
        import cv2

        success, encoded = cv2.imencode(".png", image)
        if not success:
            return False
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        encoded.tofile(path)
        return True
    except Exception:
        return False


def anh_gan_nhu_trong(image) -> bool:
    """Kiểm tra ảnh có gần như trắng/trống không để cảnh báo OCR khó đọc."""

    try:
        import cv2
        import numpy as np

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        return float(np.std(gray)) < 3.0
    except Exception:
        return False


def xoa_vung_con_dau_do(image):
    """Xóa vùng màu đỏ của con dấu để OCR không đọc nhầm chữ trong dấu.

    Hàm chỉ tác động lên vùng có màu đỏ theo HSV, giữ nguyên chữ đen của văn bản.
    """

    try:
        import cv2
        import numpy as np

        if image is None or len(image.shape) != 3:
            return image

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lower_red_1 = np.array([0, 40, 40])
        upper_red_1 = np.array([12, 255, 255])
        lower_red_2 = np.array([160, 40, 40])
        upper_red_2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(hsv, lower_red_1, upper_red_1)
        mask2 = cv2.inRange(hsv, lower_red_2, upper_red_2)
        mask = cv2.bitwise_or(mask1, mask2)
        kernel = np.ones((2, 2), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)

        cleaned = image.copy()
        cleaned[mask > 0] = [255, 255, 255]
        return cleaned
    except Exception:
        return image


def tao_bien_the_anh_ocr(image_path: str, cau_hinh: CauHinhOCR = CAU_HINH_MAC_DINH) -> list[str]:
    """Tạo danh sách ảnh biến thể để OCR thử lần lượt.

    Thứ tự ưu tiên: ảnh đã xóa dấu đỏ -> ảnh gốc -> upscaled -> enhanced -> binary.
    Nếu OCR thành công ở ảnh đầu, pipeline không cần chạy các ảnh sau.
    """

    image = doc_anh_unicode(image_path)
    if image is None:
        print(f"[WARN] Không đọc được ảnh OCR: {image_path}")
        return [image_path]

    if anh_gan_nhu_trong(image):
        print(f"[WARN] Ảnh render có vẻ trống hoặc tương phản thấp: {image_path}")

    if not cau_hinh.tao_bien_the_anh:
        return [image_path]

    try:
        import cv2

        variants: list[str] = []
        base = Path(image_path)
        variant_dir = str(base.parent)
        variant_stem = ten_file_an_toan(base.stem)

        def add_variant(suffix: str, img) -> None:
            out_path = os.path.join(variant_dir, f"{variant_stem}_{suffix}.png")
            if cau_hinh.dung_cache_anh and os.path.exists(out_path):
                variants.append(out_path)
                return
            if ghi_anh_unicode(out_path, img):
                variants.append(out_path)

        working_img = image
        if cau_hinh.xoa_con_dau_do:
            working_img = xoa_vung_con_dau_do(image)
            add_variant("ocr_cleaned", working_img)

        variants.append(image_path)

        h, w = working_img.shape[:2]
        if max(h, w) < 3200:
            upscaled = cv2.resize(working_img, None, fx=1.7, fy=1.7, interpolation=cv2.INTER_CUBIC)
            add_variant("ocr_upscaled", upscaled)

        gray = cv2.cvtColor(working_img, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 5, 75, 75)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        add_variant("ocr_enhanced", enhanced)

        binary = cv2.adaptiveThreshold(
            enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            15,
        )
        add_variant("ocr_binary", binary)

        deduped: list[str] = []
        seen: set[str] = set()
        for path in variants:
            key = os.path.abspath(str(path))
            if key not in seen:
                seen.add(key)
                deduped.append(path)
        return deduped
    except Exception as exc:
        print(f"[WARN] Không tạo được ảnh tiền xử lý OCR: {exc}")
        return [image_path]


def xoa_anh_bien_the(original_image_path: str, image_variants: list[str], cau_hinh: CauHinhOCR) -> None:
    """Xóa ảnh biến thể nếu không bật debug, tránh đầy thư mục temp."""

    if cau_hinh.luu_anh_debug:
        return
    original_abs = os.path.abspath(original_image_path)
    for variant_path in image_variants:
        try:
            if os.path.abspath(str(variant_path)) != original_abs and os.path.exists(variant_path):
                os.remove(variant_path)
        except Exception:
            pass


def sap_xep_diem_clockwise(pts):
    """Sắp xếp 4 điểm box theo thứ tự top-left, top-right, bottom-right, bottom-left."""

    import numpy as np

    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def crop_box_xoay(image, box: list[list[float]], padding: int = 8):
    """Crop vùng chữ theo box xoay/nghiêng nhẹ và thêm padding trắng quanh crop."""

    import cv2
    import numpy as np

    if image is None:
        return None
    pts = np.array(box, dtype="float32")
    rect = sap_xep_diem_clockwise(pts)
    tl, tr, br, bl = rect

    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = max(1, int(max(width_a, width_b)))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = max(1, int(max(height_a, height_b)))

    dst = np.array(
        [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, matrix, (max_width, max_height), borderMode=cv2.BORDER_REPLICATE)

    pad = max(0, int(padding))
    if pad > 0:
        if len(warped.shape) == 2:
            warped = cv2.copyMakeBorder(warped, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
        else:
            warped = cv2.copyMakeBorder(warped, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    return warped


def cv_sang_pil(image):
    """Chuyển ảnh OpenCV BGR/gray sang PIL RGB để đưa vào VietOCR."""

    import cv2
    from PIL import Image

    if image is None:
        return None
    if len(image.shape) == 2:
        return Image.fromarray(image).convert("RGB")
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).convert("RGB")
