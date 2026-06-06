"""
page_markers.py

Tiện ích chuẩn hóa page marker cho Markdown OCR/RAG.

Quy ước mới:
- Page marker chỉ dùng comment HTML: `<!-- page: n -->`.
- Không dùng `## Trang n` vì sẽ bị chunker Markdown hiểu nhầm là heading nghiệp vụ.
- Vẫn đọc được output cũ có `## Trang n` để không phá backward compatibility.
"""

from __future__ import annotations

import re


PAGE_MARKER_RE = re.compile(r"<!--\s*page\s*:\s*(\d+)\s*-->", re.IGNORECASE)
LEGACY_PAGE_HEADER_LINE_RE = re.compile(r"^\s*#{1,6}\s*Trang\s+(\d+)\s*$", re.IGNORECASE)
PAGE_BOUNDARY_RE = re.compile(
    r"(?=^\s*(?:<!--\s*page\s*:\s*\d+\s*-->|#{1,6}\s*Trang\s+\d+)\s*$)",
    re.MULTILINE | re.IGNORECASE,
)


def page_marker(page_number: int) -> str:
    """Tạo page marker canonical, không phải Markdown heading."""
    return f"<!-- page: {int(page_number)} -->"


def extraction_marker(method: str) -> str:
    """Tạo marker phương thức trích xuất dạng comment."""
    return f"<!-- extraction: {str(method).strip()} -->"


def is_page_boundary_line(line: str) -> bool:
    """True nếu dòng là page marker canonical hoặc heading page marker cũ."""
    s = str(line or "").strip()
    return bool(PAGE_MARKER_RE.fullmatch(s) or LEGACY_PAGE_HEADER_LINE_RE.match(s))


def normalize_legacy_page_headings(text: str) -> str:
    """Đổi `## Trang n` cũ thành `<!-- page: n -->` và xóa marker trùng liền kề."""
    text = str(text or "")
    lines = text.splitlines()
    out: list[str] = []

    for raw in lines:
        match = LEGACY_PAGE_HEADER_LINE_RE.match(raw)
        if not match:
            out.append(raw.rstrip())
            continue

        marker = page_marker(int(match.group(1)))
        # Nếu marker canonical cùng trang đã đứng ngay trước đó thì bỏ heading cũ.
        if out and out[-1].strip().lower() == marker.lower():
            continue
        out.append(marker)

    normalized = "\n".join(out)
    # Trường hợp output cũ có cả `## Trang n` rồi `<!-- page: n -->`, sau khi đổi sẽ trùng.
    normalized = re.sub(
        r"(?im)^(<!--\s*page\s*:\s*(\d+)\s*-->)\s*\n\s*<!--\s*page\s*:\s*\2\s*-->\s*$",
        r"\1",
        normalized,
    )
    return normalized


def strip_page_markers(text: str) -> str:
    """Xóa mọi page marker khỏi một block nội dung để gắn lại marker đúng trang."""
    text = normalize_legacy_page_headings(text)
    return PAGE_MARKER_RE.sub("", text).strip()


def clean_page_block(block: str) -> str:
    """Làm sạch một block trang nhưng giữ page marker canonical."""
    block = normalize_legacy_page_headings(block).strip()
    block = re.sub(r"\n+---\s*$", "", block).strip()
    block = re.sub(r"\n{3,}", "\n\n", block)
    return block


def make_page_block(page_number: int, *parts: str) -> str:
    """Ghép block trang theo chuẩn RAG: page marker comment + nội dung."""
    body_parts = [page_marker(page_number)]
    body_parts.extend(str(part).strip() for part in parts if str(part or "").strip())
    return clean_page_block("\n\n".join(body_parts))


def split_markdown_by_page(markdown: str) -> dict[int, str]:
    """Tách Markdown theo page marker canonical, đồng thời hỗ trợ heading cũ."""
    body = normalize_legacy_page_headings(markdown)
    markers = list(PAGE_MARKER_RE.finditer(body))
    if not markers:
        return {}

    blocks: dict[int, str] = {}
    for i, marker in enumerate(markers):
        page_no = int(marker.group(1))
        start = marker.start()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(body)
        blocks[page_no] = clean_page_block(body[start:end])
    return blocks
