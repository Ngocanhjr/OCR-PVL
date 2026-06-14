"""
page_markers.py

Chuẩn hóa page marker cho Markdown OCR/RAG.
Quy ước: chỉ dùng HTML comment `<!-- page: n -->`.
Không dùng `## Trang n` vì chunker Markdown hiểu nhầm là heading nghiệp vụ.
"""

from __future__ import annotations

import re

PAGE_MARKER_RE = re.compile(r"<!--\s*page\s*:\s*(\d+)\s*-->", re.IGNORECASE)
PAGE_BOUNDARY_RE = re.compile(
    r"(?=^\s*<!--\s*page\s*:\s*\d+\s*-->\s*$)",
    re.MULTILINE | re.IGNORECASE,
)


def page_marker(page_number: int) -> str:
    """Tạo page marker canonical."""
    return f"<!-- page: {int(page_number)} -->"


def strip_page_markers(text: str) -> str:
    """Xóa mọi page marker khỏi một block nội dung."""
    return PAGE_MARKER_RE.sub("", text).strip()


def clean_page_block(block: str) -> str:
    """Làm sạch một block trang nhưng giữ page marker canonical."""
    block = block.strip()
    block = re.sub(r"\n+---\s*$", "", block).strip()
    block = re.sub(r"\n{3,}", "\n\n", block)
    return block


def make_page_block(page_number: int, *parts: str) -> str:
    """Ghép block trang theo chuẩn RAG: page marker + nội dung."""
    body_parts = [page_marker(page_number)]
    body_parts.extend(str(p).strip() for p in parts if str(p or "").strip())
    return clean_page_block("\n\n".join(body_parts))


def split_markdown_by_page(markdown: str) -> dict[int, str]:
    """Tách Markdown theo page marker `<!-- page: n -->`."""
    markers = list(PAGE_MARKER_RE.finditer(markdown))
    if not markers:
        return {}

    blocks: dict[int, str] = {}
    for i, marker in enumerate(markers):
        page_no = int(marker.group(1))
        start = marker.start()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(markdown)
        blocks[page_no] = clean_page_block(markdown[start:end])
    return blocks
