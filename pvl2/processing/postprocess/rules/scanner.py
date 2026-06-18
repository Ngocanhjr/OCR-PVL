from __future__ import annotations

import re

from config import lam_sach_dong


SCANNER_WATERMARK_PATTERNS = [
    r"^\s*scanned\s+with\s+(cs\s*)?camscanner\s*$",
    r"^\s*scanned\s+with\s+cs\s*$",
    r"^\s*camscanner\s*$",
]


def remove_scanner_watermarks(text: str) -> str:
    """Remove common scanner app watermarks before RAG ingestion."""
    kept: list[str] = []
    for raw in str(text or "").splitlines():
        line = lam_sach_dong(raw)
        if any(re.match(p, line, flags=re.IGNORECASE) for p in SCANNER_WATERMARK_PATTERNS):
            continue
        kept.append(raw.rstrip())
    return "\n".join(kept)
