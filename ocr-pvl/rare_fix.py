"""
loi_rieng_it_gap.py
LỚP 3 - Lỗi riêng / ít gặp.

Nguyên tắc:
- Không hardcode lỗi riêng của từng file vào source chính.
- Mặc định chỉ phát hiện và ghi cảnh báo review.
- Nếu người dùng thật sự muốn tự động sửa, dùng file JSON riêng truyền qua `--loi-rieng-json`.

Ví dụ file JSON tùy chọn:
{
  "replace": {
    "chuỗi OCR sai": "chuỗi đúng"
  },
  "regex_replace": [
    {"pattern": "Số:\\s*ABC", "replacement": "Số: XYZ", "flags": "i"}
  ]
}
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from config import CauHinhOCR, lam_sach_dong, lam_sach_text, ghi_text_unicode, ten_file_an_toan


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


def ap_dung_replace_loi_rieng(text: str, rules: dict[str, Any]) -> str:
    """Áp dụng replace lỗi riêng do người dùng cấu hình ngoài source code."""

    replace_rules = rules.get("replace", {})
    if isinstance(replace_rules, dict):
        for wrong, right in replace_rules.items():
            text = text.replace(str(wrong), str(right))
    return text


def ap_dung_regex_loi_rieng(text: str, rules: dict[str, Any]) -> str:
    """Áp dụng regex replace lỗi riêng do người dùng cấu hình ngoài source code."""

    regex_rules = rules.get("regex_replace", [])
    if not isinstance(regex_rules, list):
        return text

    for item in regex_rules:
        if not isinstance(item, dict):
            continue
        pattern = item.get("pattern", "")
        replacement = item.get("replacement", "")
        flags_text = str(item.get("flags", ""))
        flags = re.IGNORECASE if "i" in flags_text.lower() else 0
        if pattern:
            try:
                text = re.sub(pattern, str(replacement), text, flags=flags)
            except re.error as exc:
                print(f"[WARN] Regex lỗi riêng không hợp lệ: {pattern} -> {exc}")
    return text


def phat_hien_so_van_ban_nghi_ngo(text: str) -> list[str]:
    """Cảnh báo số văn bản có chữ cái nằm trong phần số.

    Ví dụ `Số: 1L8/ĐTKDV-VP` có thể là OCR sai, nhưng không tự đổi thành `282`.
    """

    warnings: list[str] = []
    pattern = r"\bSố\s*:\s*([A-Za-z0-9]+\s*/\s*[^\n]+)"
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        full = lam_sach_dong(match.group(1))
        number_part = full.split("/")[0].strip()
        if re.search(r"[A-Za-z]", number_part):
            warnings.append(f"Nghi ngờ số văn bản OCR sai, cần kiểm tra ảnh gốc: Số: {full}")
    return warnings


def phat_hien_dong_con_ky_tu_la(text: str) -> list[str]:
    """Cảnh báo các dòng còn dấu ? hoặc ký tự lạ sau hậu xử lý."""

    warnings: list[str] = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = lam_sach_dong(raw)
        if not line:
            continue
        if "?" in line:
            warnings.append(f"Dòng {idx}: còn dấu '?' cần kiểm tra: {line}")
        if re.search(r"\b[0-9]+[A-Za-z][0-9]+\b", line):
            warnings.append(f"Dòng {idx}: cụm số/chữ có thể là OCR sai: {line}")
    return warnings


def phat_hien_email_nghi_ngo(text: str) -> list[str]:
    """Cảnh báo dòng giống email nhưng chưa có ký tự @."""

    warnings: list[str] = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = lam_sach_dong(raw)
        if not line:
            continue
        if re.search(r"Email", line, flags=re.IGNORECASE) and "@" not in line:
            warnings.append(f"Dòng {idx}: dòng Email chưa có @, cần kiểm tra: {line}")
    return warnings


def tao_bao_cao_review(text: str, canh_bao_bo_sung: list[str] | None = None) -> list[str]:
    """Tạo danh sách cảnh báo review cho lỗi riêng/ít gặp."""

    warnings: list[str] = []
    warnings.extend(phat_hien_so_van_ban_nghi_ngo(text))
    warnings.extend(phat_hien_dong_con_ky_tu_la(text))
    warnings.extend(phat_hien_email_nghi_ngo(text))
    if canh_bao_bo_sung:
        warnings.extend(canh_bao_bo_sung)

    # Dedupe nhưng giữ thứ tự.
    deduped: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning not in seen:
            seen.add(warning)
            deduped.append(warning)
    return deduped


def hau_xu_ly_loi_rieng(text: str, cau_hinh: CauHinhOCR) -> str:
    """Chạy lớp 3: chỉ auto-fix nếu người dùng cung cấp file JSON lỗi riêng."""

    rules = doc_quy_tac_loi_rieng(cau_hinh.file_loi_rieng_json)
    if not rules:
        return lam_sach_text(text)
    text = ap_dung_replace_loi_rieng(text, rules)
    text = ap_dung_regex_loi_rieng(text, rules)
    return lam_sach_text(text)


def ghi_bao_cao_review(file_goc: str | Path, warnings: list[str], cau_hinh: CauHinhOCR) -> str:
    """Ghi file báo cáo những dòng nên kiểm tra thủ công."""

    if not warnings:
        return ""
    stem = ten_file_an_toan(Path(file_goc).stem)
    out_path = Path(cau_hinh.thu_muc_bao_cao) / f"{stem}_review.txt"
    content = ["# OCR Review Report", "", f"File gốc: {file_goc}", "", "## Dòng/cụm cần kiểm tra"]
    content.extend([f"- {w}" for w in warnings])
    ghi_text_unicode(out_path, "\n".join(content))
    return str(out_path)
