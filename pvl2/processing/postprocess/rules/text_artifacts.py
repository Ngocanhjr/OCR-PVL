from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from processing.postprocess.rules.tables import is_table_row, is_table_separator


REPLACEMENTS_PATH = Path(__file__).resolve().parents[1] / "data" / "ctu_safe_replacements.json"


@lru_cache(maxsize=1)
def load_ctu_safe_replacements() -> dict[str, str]:
    """Load safe CTU OCR replacements from data, not code."""
    raw = json.loads(REPLACEMENTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{REPLACEMENTS_PATH} must contain a list of replacement objects")

    replacements: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("from"), str) or not isinstance(item.get("to"), str):
            raise ValueError(f"Invalid replacement entry in {REPLACEMENTS_PATH}: {item!r}")
        replacements[item["from"]] = item["to"]
    return replacements


CTU_SAFE_REPLACEMENTS = load_ctu_safe_replacements()


def normalize_toc_dot_leaders(markdown: str) -> str:
    """Remove noisy TOC dot leaders from lines with an explicit trailing page number."""
    out: list[str] = []
    pattern = re.compile(
        r"^(\s*\d{1,3}\.\s+.+?)\s+(?:[_\.·…]{3,}|(?:\s\.\s*){3,})\s*(\d{1,3})\s*$"
    )
    for line in str(markdown or "").split("\n"):
        if is_table_row(line) or is_table_separator(line):
            out.append(line)
            continue
        m = pattern.match(line)
        out.append(f"{m.group(1).rstrip()} {m.group(2)}" if m else line)
    return "\n".join(out)


def normalize_llamaparse_rag_artifacts(markdown: str) -> str:
    """Fix safe recurring OCR/LlamaParse artifacts for CTU documents."""
    text = str(markdown or "")

    text = re.sub(r"\$\s*\\(?:to|rightarrow|Rightarrow)\s*\$", "→", text)
    text = text.replace("\\rightarrow", "→")
    text = text.replace("&rarr;", "→").replace("&rightarrow;", "→")

    text = re.sub(r"\\{2,}\*", "*", text)
    text = re.sub(r"\\\*", "*", text)

    text = re.sub(r"(?<=[A-Za-zÀ-ỹ])\[\](?=[A-Za-zÀ-ỹ])", "", text)
    text = text.replace("thông bá[]", "thông báo")
    text = text.replace("thông bá có", "thông báo có")

    for old, new in CTU_SAFE_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text
