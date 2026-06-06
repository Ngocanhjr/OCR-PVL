"""
text_layer_quality.py

Kiểm tra chất lượng text layer của PDF trước khi quyết định dùng PyMuPDF text
hay phải OCR lại từ ảnh. Module này không phụ thuộc PaddleOCR, nên PDF text có thể
chạy được ngay cả khi chưa cài engine OCR nặng.
"""

from __future__ import annotations

import re

BAD_OCR_PATTERNS = [
    "BQ GIAO", "Dl)C", "DAo T~o", "TRUONGD", "D~IHQ", "cANTHa", "DQc l",
    "H~nh", "QUYETDJNH", "Gido due", "Ludt", "a6i", "b6 sung", "vAn",
    "sire khoe", "ngO'01", "Di~u", "Can Clf", "thea",
]


def is_bad_pdf_text_layer(text: str) -> bool:
    """Phát hiện text layer OCR cũ bị lỗi encoding/dấu tiếng Việt.

    Nếu trả True, pipeline local sẽ bỏ text layer và OCR lại từ ảnh. Hàm này độc lập
    với PaddleOCR để không làm lỗi import khi chỉ xử lý PDF có text copy được.
    """
    if not text or len(text.strip()) < 50:
        return True

    sample = text[:3000]
    bad_count = sum(1 for pattern in BAD_OCR_PATTERNS if pattern in sample)
    weird_chars = len(re.findall(r"[~\}\{\]\[\)\(]", sample))
    glued_upper_words = len(re.findall(r"\b[A-ZĐ]{8,}\b", sample))
    vietnamese_marks = len(re.findall(
        r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễ"
        r"ìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
        r"ùúụủũưừứựửữỳýỵỷỹđ"
        r"ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄ"
        r"ÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ"
        r"ÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]",
        sample,
    ))
    letters = len(re.findall(r"[A-Za-zÀ-ỹĐđ]", sample))
    mark_ratio = vietnamese_marks / max(letters, 1)

    if bad_count >= 3:
        return True
    if weird_chars >= 8 and mark_ratio < 0.04:
        return True
    if glued_upper_words >= 5 and mark_ratio < 0.05:
        return True
    return False
