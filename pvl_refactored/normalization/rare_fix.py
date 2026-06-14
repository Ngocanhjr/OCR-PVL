"""
rare_fix.py
LỚP 3 - Lỗi riêng / ít gặp.

Nguyên tắc:
- Không hardcode lỗi riêng của từng file vào source chính.
- Mặc định chỉ phát hiện và ghi cảnh báo review.
- Nếu người dùng muốn tự động sửa, dùng file JSON qua `--loi-rieng-json`.

Ví dụ file JSON:
{
  "replace": {"chuỗi OCR sai": "chuỗi đúng"},
  "regex_replace": [{"pattern": "Số:\\\\s*ABC", "replacement": "Số: XYZ", "flags": "i"}]
}
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from config import CauHinhOCR, ghi_text_unicode, iter_dong_sach, lam_sach_text, ten_file_an_toan


# =========================================================
# ĐỌC VÀ ÁP DỤNG RULE NGOÀI SOURCE
# =========================================================


def doc_quy_tac_loi_rieng(path: str) -> dict[str, Any]:
    """Đọc file JSON chứa lỗi riêng nếu người dùng cung cấp."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"[WARN] Không đọc được file lỗi riêng JSON: {exc}")
        return {}


def ap_dung_quy_tac_loi_rieng(text: str, rules: dict[str, Any]) -> str:
    """Áp dụng replace + regex_replace từ file JSON lỗi riêng.

    Gộp ap_dung_replace_loi_rieng + ap_dung_regex_loi_rieng vì luôn được gọi cùng nhau.
    """
    # String replace
    for wrong, right in rules.get("replace", {}).items():
        text = text.replace(str(wrong), str(right))

    # Regex replace
    for item in rules.get("regex_replace", []):
        if not isinstance(item, dict):
            continue
        pattern = item.get("pattern", "")
        replacement = item.get("replacement", "")
        flags = re.IGNORECASE if "i" in str(item.get("flags", "")).lower() else 0
        if pattern:
            try:
                text = re.sub(pattern, str(replacement), text, flags=flags)
            except re.error as exc:
                print(f"[WARN] Regex lỗi riêng không hợp lệ: {pattern} -> {exc}")
    return text


# =========================================================
# PHÁT HIỆN CẢNH BÁO
# =========================================================


def phat_hien_so_van_ban_nghi_ngo(text: str) -> list[str]:
    """Cảnh báo số văn bản có chữ cái nằm trong phần số."""
    warnings: list[str] = []
    for match in re.finditer(r"\bSố\s*:\s*([A-Za-z0-9]+\s*/\s*[^\n]+)", text, flags=re.IGNORECASE):
        full = match.group(1).strip()
        if re.search(r"[A-Za-z]", full.split("/")[0].strip()):
            warnings.append(f"Nghi ngờ số văn bản OCR sai, cần kiểm tra ảnh gốc: Số: {full}")
    return warnings


def phat_hien_dong_con_ky_tu_la(text: str) -> list[str]:
    """Cảnh báo các dòng còn dấu ? hoặc ký tự lạ sau hậu xử lý."""
    warnings: list[str] = []
    for idx, line in iter_dong_sach(text):
        if "?" in line:
            warnings.append(f"Dòng {idx}: còn dấu '?' cần kiểm tra: {line}")
        if re.search(r"\b[0-9]+[A-Za-z][0-9]+\b", line):
            warnings.append(f"Dòng {idx}: cụm số/chữ có thể là OCR sai: {line}")
    return warnings


def phat_hien_email_nghi_ngo(text: str) -> list[str]:
    """Cảnh báo dòng giống email nhưng chưa có ký tự @."""
    return [
        f"Dòng {idx}: dòng Email chưa có @, cần kiểm tra: {line}"
        for idx, line in iter_dong_sach(text)
        if re.search(r"Email", line, flags=re.IGNORECASE) and "@" not in line
    ]


def tao_bao_cao_review(text: str, canh_bao_bo_sung: list[str] | None = None) -> list[str]:
    """Tạo danh sách cảnh báo review cho lỗi riêng/ít gặp, dedupe giữ thứ tự."""
    raw = (
        phat_hien_so_van_ban_nghi_ngo(text)
        + phat_hien_dong_con_ky_tu_la(text)
        + phat_hien_email_nghi_ngo(text)
        + (canh_bao_bo_sung or [])
    )
    seen: set[str] = set()
    return [w for w in raw if not (w in seen or seen.add(w))]  # type: ignore[func-returns-value]


# =========================================================
# ENTRY POINTS
# =========================================================


def hau_xu_ly_loi_rieng(text: str, cau_hinh: CauHinhOCR) -> str:
    """Chạy lớp 3: chỉ auto-fix nếu người dùng cung cấp file JSON lỗi riêng."""
    rules = doc_quy_tac_loi_rieng(cau_hinh.file_loi_rieng_json)
    if rules:
        text = ap_dung_quy_tac_loi_rieng(text, rules)
    return lam_sach_text(text)


def ghi_bao_cao_review(file_goc: str | Path, warnings: list[str], cau_hinh: CauHinhOCR) -> str:
    """Ghi file báo cáo những dòng nên kiểm tra thủ công."""
    if not warnings:
        return ""
    stem = ten_file_an_toan(Path(file_goc).stem)
    out_path = Path(cau_hinh.thu_muc_bao_cao) / f"{stem}_review.txt"
    content = ["# OCR Review Report", "", f"File gốc: {file_goc}", "", "## Dòng/cụm cần kiểm tra"]
    content.extend(f"- {w}" for w in warnings)
    ghi_text_unicode(out_path, "\n".join(content))
    return str(out_path)
