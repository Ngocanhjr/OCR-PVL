from __future__ import annotations

import re


def normalize_form_layout(markdown: str) -> str:
    """Make OCR form fields readable without guessing filled values."""
    text = str(markdown or "")
    text = re.sub(r"\.{6,}", "________", text)
    text = re.sub(r"\s+…{2,}", " ________", text)

    text = re.sub(r"\b(Nam|Nữ|Có|Không)\s+(?<![A-Za-zÀ-ỹ])[O0□☐](?![A-Za-zÀ-ỹ])", r"\1 [ ]", text)
    text = re.sub(r"(?<![A-Za-zÀ-ỹ])[O0□☐](?![A-Za-zÀ-ỹ])\s+(Nam|Nữ|Có|Không)\b", r"[ ] \1", text)

    text = re.sub(
        r"(__+)\s+(Họ và tên|Ngày sinh|Giới tính|CCCD|Nơi cấp|Tên cơ sở|Hệ đào tạo|Ngành|Mã ngành|Loại hình đào tạo)",
        r"\1\n\2",
        text,
        flags=re.IGNORECASE,
    )
    return text
