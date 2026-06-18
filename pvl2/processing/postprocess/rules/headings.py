from __future__ import annotations

import re

from processing.postprocess.rules.tables import is_table_row, is_table_separator


def normalize_ctu_markdown_headings(markdown: str) -> str:
    """Normalize light CTU heading patterns without touching Markdown tables."""
    out: list[str] = []
    in_table = False
    for raw in str(markdown or "").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if is_table_row(stripped) or is_table_separator(stripped):
            in_table = True
            out.append(line)
            continue
        if not stripped:
            in_table = False
            out.append(line)
            continue
        if in_table or stripped.startswith("<!--"):
            out.append(line)
            continue

        m = re.match(r"^\*\*(\d+(?:\.\d+)+\s+.+?)\*\*\s*$", stripped)
        if m:
            label = m.group(1).rstrip(" :")
            out.append("##### " + label + (":" if m.group(1).rstrip().endswith(":") else ""))
            continue

        m = re.match(r"^\*\*(\d+\.\s+.+?)\*\*\s*$", stripped)
        if m:
            out.append("#### " + m.group(1).strip())
            continue

        out.append(line)
    return "\n".join(out)
