"""
normalize_existing_markdown.py

Tiện ích hậu xử lý lại file Markdown đã OCR/parse mà không cần chạy OCR lại.
Dùng khi bạn đã có file .md từ OCR_PVL/LlamaParse và chỉ muốn làm sạch để đưa vào RAG:

    python normalize_existing_markdown.py QuyTrinh4-Congtacsinhvien.md -o QuyTrinh4-Congtacsinhvien_rag_clean.md

Script này giữ nguyên page marker dạng `<!-- page: n -->` để phục vụ citation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from processing.table_form_postprocess import postprocess_final_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Làm sạch Markdown OCR/LlamaParse hiện có để dùng cho RAG, không chạy OCR lại."
    )
    parser.add_argument("input", type=Path, help="Đường dẫn file Markdown input.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Đường dẫn file output. Nếu bỏ trống sẽ tạo <input_stem>_rag_clean.md",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_path: Path = args.input
    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file input: {input_path}")
    if input_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("Input nên là file Markdown/text đã OCR/parse.")

    output_path: Path = args.output or input_path.with_name(f"{input_path.stem}_rag_clean.md")
    text = input_path.read_text(encoding="utf-8")
    cleaned = postprocess_final_markdown(text)
    output_path.write_text(cleaned, encoding="utf-8")
    print(f"[OK] Đã ghi file RAG-clean Markdown: {output_path}")


if __name__ == "__main__":
    main()
