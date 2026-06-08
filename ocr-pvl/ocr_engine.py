"""
ocr_dong_co.py
Động cơ OCR: PaddleOCR detection/recognition + VietOCR recognition.

Tái sử dụng các phần tốt từ source cũ:
- Lazy-load PaddleOCR/VietOCR để không khởi tạo nhiều lần.
- PaddleOCR detect box, VietOCR nhận dạng crop cho tiếng Việt.
- Fallback PaddleOCR recognition nếu dòng nghi có @, URL, Email, ký tự đặc biệt.
- Hỗ trợ fallback nhiều ngôn ngữ PaddleOCR: vi, latin, en.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import re


BAD_OCR_PATTERNS = [
    "BQ GIAO",
    "Dl)C",
    "DAo T~o",
    "TRUONGD",
    "D~IHQ",
    "cANTHa",
    "DQc l",
    "H~nh",
    "QUYETDJNH",
    "Gido due",
    "Ludt",
    "a6i",
    "b6 sung",
    "vAn",
    "sire khoe",
    "ngO'01",
    "Di~u",
    "Can Clf",
    "thea",
]


EXPECTED_VIETNAMESE_KEYWORDS = [
    "BỘ GIÁO DỤC",
    "ĐÀO TẠO",
    "TRƯỜNG ĐẠI HỌC CẦN THƠ",
    "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "Độc lập",
    "Tự do",
    "Hạnh phúc",
    "QUYẾT ĐỊNH",
    "Điều",
    "Cần Thơ",
]


def is_bad_pdf_text_layer(text: str) -> bool:
    """
    Phát hiện PDF scan có text layer OCR cũ bị lỗi.
    Nếu text layer bị lỗi thì không dùng page.get_text(), mà phải OCR lại từ ảnh.
    """

    if not text or len(text.strip()) < 50:
        return True

    sample = text[:3000]

    bad_count = 0
    for pattern in BAD_OCR_PATTERNS:
        if pattern in sample:
            bad_count += 1

    # Đếm ký tự lạ hay xuất hiện khi OCR/encoding hỏng
    weird_chars = len(re.findall(r"[~\}\{\]\[\)\(]", sample))

    # Đếm từ bị dính liền kiểu TRUONGDAIHOC, CONGHOA, QUYETDJNH
    glued_upper_words = len(re.findall(r"\b[A-ZĐ]{8,}\b", sample))

    # Tỷ lệ ký tự tiếng Việt có dấu
    vietnamese_marks = len(re.findall(
        r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễ"
        r"ìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
        r"ùúụủũưừứựửữỳýỵỷỹđ"
        r"ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄ"
        r"ÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ"
        r"ÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]",
        sample
    ))

    letters = len(re.findall(r"[A-Za-zÀ-ỹĐđ]", sample))
    mark_ratio = vietnamese_marks / max(letters, 1)

    # Nếu có nhiều mẫu lỗi rõ ràng thì chắc chắn text layer hỏng
    if bad_count >= 3:
        return True

    # Nếu nhiều ký tự lạ + ít dấu tiếng Việt
    if weird_chars >= 8 and mark_ratio < 0.04:
        return True

    # Nếu nhiều chữ in hoa dính liền bất thường
    if glued_upper_words >= 5 and mark_ratio < 0.05:
        return True

    return False

# Set env trước khi import paddle để ổn định CPU Windows.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_mkldnn", "0")
os.environ.setdefault("FLAGS_use_onednn", "0")
os.environ.setdefault("FLAGS_enable_onednn", "0")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

try:
    from paddleocr import PaddleOCR
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "Không import được PaddleOCR. Cài bằng: pip install paddleocr==2.9.1 paddlepaddle"
    ) from exc

from config import CauHinhOCR, CAU_HINH_MAC_DINH, lam_sach_dong, lam_sach_text, ten_file_an_toan
from common_fix import hau_xu_ly_loi_chung, nghi_ngo_co_ky_tu_dac_biet
from image_preprocess import (
    crop_box_xoay,
    cv_sang_pil,
    doc_anh_unicode,
    ghi_anh_unicode,
    tao_bien_the_anh_ocr,
    xoa_anh_bien_the,
)

_OCR_ENGINES: dict[str, PaddleOCR] = {}
_VIETOCR_ENGINE: Any | None = None


def ap_dung_moi_truong_paddle(cau_hinh: CauHinhOCR = CAU_HINH_MAC_DINH) -> None:
    """Áp dụng cấu hình runtime cho PaddleOCR, nhất là tắt MKLDNN/OneDNN trên CPU yếu."""

    if cau_hinh.bat_mkldnn:
        os.environ["FLAGS_use_mkldnn"] = "1"
        os.environ["FLAGS_enable_mkldnn"] = "1"
        os.environ["FLAGS_use_onednn"] = "1"
        os.environ["FLAGS_enable_onednn"] = "1"
    else:
        os.environ["FLAGS_use_mkldnn"] = "0"
        os.environ["FLAGS_enable_mkldnn"] = "0"
        os.environ["FLAGS_use_onednn"] = "0"
        os.environ["FLAGS_enable_onednn"] = "0"

    os.environ["OMP_NUM_THREADS"] = str(max(1, int(cau_hinh.so_luong_cpu_threads)))
    os.environ["MKL_NUM_THREADS"] = str(max(1, int(cau_hinh.so_luong_cpu_threads)))


def lay_paddle_ocr(cau_hinh: CauHinhOCR = CAU_HINH_MAC_DINH, lang: str | None = None) -> PaddleOCR:
    """Khởi tạo PaddleOCR lazy-load và cache theo ngôn ngữ."""

    ap_dung_moi_truong_paddle(cau_hinh)
    selected_lang = str(lang or cau_hinh.ngon_ngu_ocr or "vi").strip() or "vi"

    if selected_lang not in _OCR_ENGINES:
        print(f"[INIT] PaddleOCR lang={selected_lang}, gpu={cau_hinh.dung_gpu}")
        base_kwargs = dict(
            use_angle_cls=True,
            lang=selected_lang,
            use_gpu=cau_hinh.dung_gpu,
            show_log=False,
        )
        stable_kwargs = dict(
            enable_mkldnn=cau_hinh.bat_mkldnn,
            cpu_threads=cau_hinh.so_luong_cpu_threads,
            drop_score=cau_hinh.ocr_drop_score,
            det_db_thresh=cau_hinh.det_db_thresh,
            det_db_box_thresh=cau_hinh.det_db_box_thresh,
            det_db_unclip_ratio=cau_hinh.det_db_unclip_ratio,
            use_dilation=True,
            det_limit_side_len=2048,
        )
        try:
            engine = PaddleOCR(**base_kwargs, **stable_kwargs)
        except TypeError:
            try:
                engine = PaddleOCR(
                    **base_kwargs,
                    enable_mkldnn=cau_hinh.bat_mkldnn,
                    cpu_threads=cau_hinh.so_luong_cpu_threads,
                    drop_score=cau_hinh.ocr_drop_score,
                )
            except TypeError:
                engine = PaddleOCR(**base_kwargs)
        _OCR_ENGINES[selected_lang] = engine

    return _OCR_ENGINES[selected_lang]


def lay_vietocr(cau_hinh: CauHinhOCR = CAU_HINH_MAC_DINH) -> Any | None:
    """Khởi tạo VietOCR lazy-load; lỗi thì trả None để fallback PaddleOCR."""

    global _VIETOCR_ENGINE
    if not cau_hinh.dung_vietocr:
        return None
    if _VIETOCR_ENGINE is not None:
        return _VIETOCR_ENGINE

    try:
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor
    except Exception as exc:
        print(f"[WARN] Chưa cài VietOCR hoặc import lỗi: {exc}")
        print("       Cài thêm: pip install vietocr torch torchvision pillow")
        return None

    try:
        model_name = str(cau_hinh.vietocr_model or "vgg_transformer").strip() or "vgg_transformer"
        print(f"[INIT] VietOCR model={model_name}, gpu={cau_hinh.dung_gpu}")
        config = Cfg.load_config_from_name(model_name)
        config["device"] = "cuda:0" if cau_hinh.dung_gpu else "cpu"
        if cau_hinh.vietocr_weights:
            config["weights"] = cau_hinh.vietocr_weights
        _VIETOCR_ENGINE = Predictor(config)
        return _VIETOCR_ENGINE
    except Exception as exc:
        print(f"[WARN] Không khởi tạo được VietOCR, fallback PaddleOCR: {exc}")
        return None


def la_so(value: Any) -> bool:
    """Kiểm tra một giá trị có ép sang float được không."""

    try:
        float(value)
        return True
    except Exception:
        return False


def giong_diem(obj: Any) -> bool:
    """Kiểm tra object có giống một điểm [x, y] hay không."""

    return isinstance(obj, (list, tuple)) and len(obj) >= 2 and la_so(obj[0]) and la_so(obj[1])


def giong_box(obj: Any) -> bool:
    """Kiểm tra object có giống box 4 điểm của PaddleOCR hay không."""

    return isinstance(obj, (list, tuple)) and len(obj) >= 4 and all(giong_diem(p) for p in obj[:4])


def duyet_box_paddle(result: Any):
    """Duyệt kết quả PaddleOCR detection ở nhiều format khác nhau và yield box."""

    if result is None:
        return
    queue = [result]
    seen_ids: set[int] = set()
    while queue:
        obj = queue.pop(0)
        if obj is None:
            continue
        obj_id = id(obj)
        if obj_id in seen_ids:
            continue
        seen_ids.add(obj_id)

        if giong_box(obj):
            yield [[float(p[0]), float(p[1])] for p in obj[:4]]
            continue
        if isinstance(obj, dict):
            for value in obj.values():
                if isinstance(value, (list, tuple, dict)):
                    queue.append(value)
            continue
        if isinstance(obj, (list, tuple)):
            for item in obj:
                if isinstance(item, (list, tuple, dict)):
                    queue.append(item)


def thong_so_box(box: list[list[float]]) -> tuple[float, float, float, float, float, float]:
    """Tính left/top/right/bottom/center_y/height của box OCR."""

    xs = [float(p[0]) for p in box]
    ys = [float(p[1]) for p in box]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    height = max(1.0, bottom - top)
    center_y = (top + bottom) / 2.0
    return left, top, right, bottom, center_y, height


def sap_xep_box_theo_thu_tu_doc(boxes: list[list[list[float]]]) -> list[list[list[float]]]:
    """Sắp xếp box theo thứ tự đọc tự nhiên: trên xuống, trái sang phải."""

    if not boxes:
        return []
    heights = sorted(thong_so_box(box)[5] for box in boxes)
    median_height = heights[len(heights) // 2]
    line_threshold = max(8.0, median_height * 0.65)

    items = []
    for box in boxes:
        left, top, _, _, center_y, _ = thong_so_box(box)
        items.append({"box": box, "left": left, "top": top, "center_y": center_y})

    items.sort(key=lambda item: (item["top"], item["left"]))
    lines: list[list[dict[str, Any]]] = []
    for item in items:
        placed = False
        for line in lines:
            line_center = sum(x["center_y"] for x in line) / len(line)
            if abs(item["center_y"] - line_center) <= line_threshold:
                line.append(item)
                placed = True
                break
        if not placed:
            lines.append([item])

    sorted_boxes: list[list[list[float]]] = []
    for line in lines:
        line.sort(key=lambda item: item["left"])
        sorted_boxes.extend([item["box"] for item in line])
    return sorted_boxes


def loai_trung_box(boxes: list[list[list[float]]]) -> list[list[list[float]]]:
    """Loại box trùng nhau nhưng giữ thứ tự đầu tiên."""

    deduped: list[list[list[float]]] = []
    seen: set[tuple[int, ...]] = set()
    for box in boxes:
        flat: list[int] = []
        for p in box:
            flat.extend([round(float(p[0])), round(float(p[1]))])
        key = tuple(flat)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(box)
    return deduped


def chay_detect_paddle(engine: PaddleOCR, image_input: Any) -> list[list[list[float]]]:
    """Chạy PaddleOCR detection only và trả danh sách box đã sắp xếp."""

    try:
        result = engine.ocr(image_input, det=True, rec=False, cls=False)
    except TypeError:
        try:
            result = engine.ocr(image_input, rec=False)
        except TypeError:
            result = engine.ocr(image_input)
    boxes = loai_trung_box(list(duyet_box_paddle(result)))
    return sap_xep_box_theo_thu_tu_doc(boxes)


def nhan_dang_crop_vietocr(vietocr_engine: Any, crop_image) -> str:
    """Nhận dạng một crop bằng VietOCR."""

    pil_image = cv_sang_pil(crop_image)
    if pil_image is None or vietocr_engine is None:
        return ""
    try:
        text = vietocr_engine.predict(pil_image)
    except TypeError:
        text = vietocr_engine.predict(pil_image, return_prob=False)
    return lam_sach_dong(text)


def rut_text_tu_dong_paddle(obj: Any) -> str | None:
    """Rút text từ một dòng kết quả PaddleOCR phổ biến: [box, (text, score)]."""

    if isinstance(obj, dict):
        for key in ("text", "transcription"):
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    if isinstance(obj, (list, tuple)) and len(obj) >= 2:
        candidate = obj[1]
        if isinstance(candidate, (list, tuple)) and candidate:
            if isinstance(candidate[0], str) and candidate[0].strip():
                return candidate[0]
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


def duyet_text_paddle(result: Any):
    """Duyệt kết quả PaddleOCR ở nhiều format khác nhau và yield text."""

    if result is None:
        return
    queue = [result]
    seen_ids: set[int] = set()
    while queue:
        obj = queue.pop(0)
        if obj is None:
            continue
        obj_id = id(obj)
        if obj_id in seen_ids:
            continue
        seen_ids.add(obj_id)

        direct_text = rut_text_tu_dong_paddle(obj)
        if direct_text:
            yield direct_text
            continue
        if isinstance(obj, str):
            if obj.strip():
                yield obj
            continue
        if isinstance(obj, dict):
            for value in obj.values():
                if isinstance(value, (list, tuple, dict, str)):
                    queue.append(value)
            continue
        if isinstance(obj, (list, tuple)):
            for item in obj:
                if isinstance(item, (list, tuple, dict, str)):
                    queue.append(item)


def nhan_dang_crop_paddle(engine: PaddleOCR, crop_image) -> str:
    """Nhận dạng lại một crop bằng PaddleOCR recognition, dùng cho dòng có ký tự đặc biệt."""

    try:
        result = engine.ocr(crop_image, det=False, rec=True, cls=False)
    except TypeError:
        try:
            result = engine.ocr(crop_image, det=False, rec=True)
        except TypeError:
            result = engine.ocr(crop_image)
    texts = [lam_sach_dong(t) for t in duyet_text_paddle(result) if lam_sach_dong(t)]
    return lam_sach_dong(" ".join(texts))


def chon_text_tot_hon(viet_text: str, paddle_text: str) -> str:
    """Chọn kết quả tốt hơn giữa VietOCR và PaddleOCR cho dòng nghi có ký tự đặc biệt."""

    viet_text = hau_xu_ly_loi_chung(viet_text)
    paddle_text = hau_xu_ly_loi_chung(paddle_text)
    if not paddle_text:
        return viet_text
    if "@" in paddle_text and "@" not in viet_text:
        return paddle_text
    if paddle_text.count("?") < viet_text.count("?"):
        return paddle_text
    if len(paddle_text) > len(viet_text) + 5 and "?" not in paddle_text:
        return paddle_text
    return viet_text


def nhan_dang_crop(vietocr_engine: Any, paddle_engine: PaddleOCR, crop_image, cau_hinh: CauHinhOCR) -> str:
    """Nhận dạng crop bằng VietOCR và fallback PaddleOCR nếu nghi lỗi ký tự đặc biệt."""

    if vietocr_engine is not None:
        viet_text = nhan_dang_crop_vietocr(vietocr_engine, crop_image)
    else:
        viet_text = ""

    if not viet_text:
        return hau_xu_ly_loi_chung(nhan_dang_crop_paddle(paddle_engine, crop_image))

    viet_text = hau_xu_ly_loi_chung(viet_text)
    if not cau_hinh.fallback_ky_tu_dac_biet:
        return viet_text
    if not nghi_ngo_co_ky_tu_dac_biet(viet_text):
        return viet_text

    try:
        paddle_text = nhan_dang_crop_paddle(paddle_engine, crop_image)
    except Exception:
        paddle_text = ""
    return chon_text_tot_hon(viet_text, paddle_text)


def luu_crop_debug(crop_image, image_path: str, index: int, cau_hinh: CauHinhOCR) -> None:
    """Lưu crop chữ để debug nếu bật `luu_crop_vietocr`."""

    if not cau_hinh.luu_crop_vietocr:
        return
    try:
        crop_dir = os.path.join(cau_hinh.thu_muc_output, "vietocr_crops")
        os.makedirs(crop_dir, exist_ok=True)
        stem = ten_file_an_toan(Path(image_path).stem)
        out_path = os.path.join(crop_dir, f"{stem}_crop_{index:04d}.png")
        ghi_anh_unicode(out_path, crop_image)
    except Exception:
        pass


def ocr_anh_bang_paddle_vietocr(image_path: str, cau_hinh: CauHinhOCR = CAU_HINH_MAC_DINH) -> str:
    """OCR ảnh bằng PaddleOCR detect box + VietOCR recognize crop."""

    vietocr_engine = lay_vietocr(cau_hinh)
    image_variants = tao_bien_the_anh_ocr(image_path, cau_hinh=cau_hinh)

    candidate_langs: list[str] = []
    for lang in [cau_hinh.ngon_ngu_ocr, "vi", "latin", "en"]:
        lang = str(lang or "").strip()
        if lang and lang not in candidate_langs:
            candidate_langs.append(lang)

    last_error = ""
    try:
        for lang in candidate_langs:
            try:
                paddle_engine = lay_paddle_ocr(cau_hinh, lang=lang)
            except Exception as exc:
                last_error = str(exc)
                print(f"[WARN] Không khởi tạo được PaddleOCR lang={lang}: {exc}")
                continue

            for variant_index, variant_path in enumerate(image_variants, start=1):
                image = doc_anh_unicode(variant_path)
                if image is None:
                    continue
                try:
                    boxes = chay_detect_paddle(paddle_engine, variant_path)
                except Exception as exc:
                    last_error = str(exc)
                    print(f"[WARN] PaddleOCR detection lỗi với {variant_path}, lang={lang}: {exc}")
                    continue
                if not boxes:
                    continue

                texts: list[str] = []
                for box_index, box in enumerate(boxes, start=1):
                    crop = crop_box_xoay(image, box, padding=cau_hinh.padding_crop)
                    if crop is None:
                        continue
                    luu_crop_debug(crop, variant_path, box_index, cau_hinh)
                    text = nhan_dang_crop(vietocr_engine, paddle_engine, crop, cau_hinh)
                    if text:
                        texts.append(text)

                if texts:
                    if variant_index > 1:
                        print(f"[INFO] OCR thành công bằng ảnh biến thể {variant_index}: {variant_path}")
                    if lang != cau_hinh.ngon_ngu_ocr:
                        print(f"[INFO] OCR thành công bằng fallback lang={lang}")
                    return lam_sach_text("\n".join(texts))
    finally:
        xoa_anh_bien_the(image_path, image_variants, cau_hinh)

    if last_error:
        print(f"[WARN] OCR không đọc được text từ {image_path}. Lỗi cuối: {last_error}")
    return ""


def ocr_anh_paddle_thuan(image_path: str, cau_hinh: CauHinhOCR = CAU_HINH_MAC_DINH) -> str:
    """OCR ảnh bằng PaddleOCR thuần, dùng làm fallback nếu VietOCR không chạy."""

    image_variants = tao_bien_the_anh_ocr(image_path, cau_hinh=cau_hinh)
    candidate_langs: list[str] = []
    for lang in [cau_hinh.ngon_ngu_ocr, "latin", "en", "vi"]:
        lang = str(lang or "").strip()
        if lang and lang not in candidate_langs:
            candidate_langs.append(lang)

    try:
        for lang in candidate_langs:
            try:
                engine = lay_paddle_ocr(cau_hinh, lang=lang)
            except Exception as exc:
                print(f"[WARN] Không khởi tạo được PaddleOCR lang={lang}: {exc}")
                continue
            for variant_path in image_variants:
                try:
                    result = engine.ocr(variant_path, cls=True)
                    texts = [lam_sach_dong(t) for t in duyet_text_paddle(result) if lam_sach_dong(t)]
                except Exception as exc:
                    print(f"[WARN] PaddleOCR lỗi với {variant_path}, lang={lang}: {exc}")
                    texts = []
                if texts:
                    return hau_xu_ly_loi_chung("\n".join(texts))
    finally:
        xoa_anh_bien_the(image_path, image_variants, cau_hinh)
    return ""
