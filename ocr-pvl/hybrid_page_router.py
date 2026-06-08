"""
hybrid_page_router.py

Router cấp trang cho PDF:
- Trang văn bản thường: dùng pipeline local TableSafe (PyMuPDF text-only hoặc Paddle+VietOCR).
- Trang có bảng/lưu đồ thật: dùng LlamaParse để tạo Markdown table/layout.

Điểm quan trọng:
- Không dùng PyMuPDF để tạo bảng.
- Không gọi LlamaParse cho trang văn bản thường, tránh sinh bảng giả và tiết kiệm credits.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional

from config import CAU_HINH_MAC_DINH, ghi_text_unicode, tao_thu_muc_can_thiet, ten_file_an_toan, tinh_checksum
from document_page_analyzer import analyze_pdf_pages, group_contiguous_pages, table_pages_from_signals
from llamaparse_engine import LlamaParseConfig, parse_with_llamaparse
from table_form_postprocess import postprocess_final_markdown
from apply_metadata import apply_metadata_to_markdown
from validate_metadata import validate_metadata_text
from page_markers import (
    PAGE_MARKER_RE,
    clean_page_block,
    make_page_block,
    split_markdown_by_page,
    strip_page_markers,
)


def parse_manual_pages(value: str | None) -> list[int]:
    """Đọc danh sách trang thủ công, ví dụ `4,6,8-10` thành list[int]."""
    if not value:
        return []

    pages: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
            pages.update(range(min(start, end), max(start, end) + 1))
        else:
            pages.add(int(part))
    return sorted(p for p in pages if p >= 1)



def split_local_markdown_by_page(body: str) -> dict[int, str]:
    """Tách body Markdown local theo page marker comment, vẫn hỗ trợ output cũ `## Trang n`."""
    return split_markdown_by_page(body)


def split_llama_markdown_by_page(markdown: str, expected_pages: list[int]) -> dict[int, str]:
    """Tách Markdown LlamaParse theo page marker và gán lại số trang nếu cần.

    Một số phiên bản SDK trả marker theo số trang gốc, một số có thể trả thứ tự trong
    page range. Hàm này ưu tiên marker khớp expected_pages; nếu không khớp thì map
    theo thứ tự expected_pages để không làm lệch trang khi ghép output.
    """
    markers = list(PAGE_MARKER_RE.finditer(markdown))
    if not markers:
        return {expected_pages[0]: make_page_block(expected_pages[0], markdown)} if expected_pages else {}

    raw_blocks: list[tuple[int, str]] = []
    for i, marker in enumerate(markers):
        page_no = int(marker.group(1))
        start = marker.start()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(markdown)
        raw_blocks.append((page_no, markdown[start:end].strip()))

    result: dict[int, str] = {}
    marker_pages = [p for p, _ in raw_blocks]
    if set(marker_pages).intersection(expected_pages):
        for page_no, block in raw_blocks:
            if page_no in expected_pages:
                result[page_no] = make_page_block(page_no, "<!-- extraction: llamaparse_table_page -->", strip_page_markers(block))
        return result

    for page_no, (_, block) in zip(expected_pages, raw_blocks):
        # Loại marker cũ rồi gắn marker gốc chính xác.
        result[page_no] = make_page_block(page_no, "<!-- extraction: llamaparse_table_page -->", strip_page_markers(block))
    return result


def local_body_for_range(
    input_path: str | Path,
    output_dir: str | Path,
    page_start: int,
    page_end: int,
    base_config=None,
):
    """Chạy pipeline local TableSafe cho một khoảng trang PDF.

    Hàm dùng `main.xu_ly_pdf` nhưng cấu hình page_start/page_end theo khoảng cần xử lý.
    Pipeline local đã bị tắt hoàn toàn phần tạo bảng bằng PyMuPDF.

    `base_config` giúp main.py truyền các tùy chọn CLI như DPI, language, force OCR,
    VietOCR model... vào router TableSafe, thay vì luôn dùng default cứng.
    """
    from main import xu_ly_pdf

    out_dir = Path(output_dir)
    cfg_source = base_config or CAU_HINH_MAC_DINH
    cfg = replace(
        cfg_source,
        thu_muc_output=str(out_dir),
        thu_muc_anh_tam=str(out_dir / "temp_images"),
        thu_muc_bao_cao=str(out_dir / "review_reports"),
        trang_bat_dau=page_start,
        trang_ket_thuc=page_end,
    )
    tao_thu_muc_can_thiet(cfg)
    return xu_ly_pdf(input_path, cfg)


def llama_body_for_range(
    input_path: str | Path,
    page_start: int,
    page_end: int,
    llama_tier: str = "agentic",
    export_tables_as_xlsx: bool = False,
    preserve_spatial_text: bool = False,
    disable_cache: bool = False,
    aggressive_tables: bool = False,
    repair_false_tables: bool = True,
) -> dict[int, str]:
    """Gọi LlamaParse cho một khoảng trang có bảng/lưu đồ thật và trả về dict page->markdown."""
    expected_pages = list(range(page_start, page_end + 1))
    cfg = LlamaParseConfig(
        tier=llama_tier,  # type: ignore[arg-type]
        page_start=page_start,
        page_end=page_end,
        export_tables_as_xlsx=export_tables_as_xlsx,
        preserve_spatial_text=preserve_spatial_text,
        disable_cache=disable_cache,
        aggressive_table_extraction=aggressive_tables,
        repair_false_tables=repair_false_tables,
        specialized_chart_parsing="agentic_plus" if llama_tier == "agentic_plus" else None,
    )
    markdown = parse_with_llamaparse(input_path, cfg)
    return split_llama_markdown_by_page(markdown, expected_pages)


def build_table_safe_metadata(
    input_path: str | Path,
    total_pages: int,
    page_start: int,
    page_end: int,
    local_pages: list[int],
    llama_pages: list[int],
    engine_mode: str,
) -> str:
    """Tạo metadata đầu file cho output TableSafe."""
    path = Path(input_path)
    lines = [
        "# PDF / Image Text Document",
        "",
        "## Metadata",
        "",
        f"- Source file: `{path}`",
        f"- Source name: `{path.name}`",
        "- Extraction mode: ocr_ctu_tablesafe_v2",
        "- Parser local: PyMuPDF text-only; no PyMuPDF table extraction",
        "- Parser table pages: LlamaParse only",
        "- OCR engine for scan local: PaddleOCR detection + VietOCR recognition; fallback PaddleOCR recognition",
        f"- Engine mode: {engine_mode}",
        f"- Source total pages: {total_pages}",
        f"- Processed pages: {page_start}-{page_end}",
        f"- Local text/OCR pages: {local_pages}",
        f"- LlamaParse table pages: {llama_pages}",
        f"- Checksum: {tinh_checksum(path)}",
        "",
        "## Extracted Text",
        "",
    ]
    return "\n".join(lines)


def get_pdf_total_pages(pdf_path: str | Path) -> int:
    """Trả số trang của PDF bằng PyMuPDF."""
    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        return len(doc)
    finally:
        doc.close()


def route_table_pages(
    input_path: str | Path,
    page_start: Optional[int],
    page_end: Optional[int],
    manual_table_pages: str | None = None,
    detect_tables: bool = True,
) -> tuple[list[int], list[str]]:
    """Xác định trang nào sẽ dùng LlamaParse.

    Ưu tiên `manual_table_pages` nếu người dùng chỉ định. Nếu không, dùng detector
    layout an toàn trong `document_page_analyzer.py`.
    """
    manual = parse_manual_pages(manual_table_pages)
    if manual:
        return manual, [f"manual_table_pages:{manual}"]

    if not detect_tables:
        return [], ["detect_tables_disabled"]

    signals = analyze_pdf_pages(input_path, page_start, page_end)
    direct_pages = [s.page_number for s in signals if s.likely_table or getattr(s, "likely_form", False)]
    table_direct_pages = [s.page_number for s in signals if s.likely_table]
    form_direct_pages = [s.page_number for s in signals if getattr(s, "likely_form", False)]
    pages = table_pages_from_signals(signals, expand_contiguous_tables=True)
    logs = [
        f"page={s.page_number} likely_table={s.likely_table} likely_form={getattr(s, 'likely_form', False)} "
        f"vector={s.vector_line_count} raster_table={s.raster_line_score:.2f} "
        f"raster_form={getattr(s, 'raster_form_score', 0.0):.2f} "
        f"h={getattr(s, 'raster_horizontal_lines', 0)} v={getattr(s, 'raster_vertical_lines', 0)} "
        f"keyword={s.keyword_score} form_score={getattr(s, 'form_score', 0)} reasons={s.reasons}"
        for s in signals
    ]
    if pages != direct_pages:
        logs.append(f"expanded_table_or_form_pages table_direct={table_direct_pages} form_direct={form_direct_pages} expanded={pages}")
    return pages, logs


def run_table_safe_pdf(
    input_path: str | Path,
    output_path: str | Path,
    engine: str = "auto-page",
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
    manual_table_pages: str | None = None,
    llama_tier: str = "agentic",
    export_tables_as_xlsx: bool = False,
    preserve_spatial_text: bool = False,
    disable_cache: bool = False,
    aggressive_tables: bool = False,
    repair_false_tables: bool = True,
    base_config=None,
) -> Path:
    """Chạy pipeline TableSafe chính cho PDF.

    engine:
    - local: toàn bộ trang dùng local text/OCR, không tạo bảng PyMuPDF.
    - llamaparse: toàn bộ trang dùng LlamaParse.
    - auto-page: detector chọn riêng trang bảng/lưu đồ để dùng LlamaParse.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if input_path.suffix.lower() != ".pdf":
        raise ValueError("TableSafe cấp trang hiện tối ưu cho PDF. Ảnh/DOCX hãy chạy main.py --engine local hoặc --engine llamaparse.")

    engine = engine.lower().strip()
    if engine not in {"local", "llamaparse", "auto-page"}:
        raise ValueError("engine phải là: local | llamaparse | auto-page")

    total_pages = get_pdf_total_pages(input_path)
    start = max(1, int(page_start or 1))
    end = min(total_pages, int(page_end or total_pages))
    if end < start:
        end = start
    all_pages = list(range(start, end + 1))

    if engine == "llamaparse":
        llama_pages = all_pages
        logs = ["engine_llamaparse_all_pages"]
    elif engine == "local":
        llama_pages = []
        logs = ["engine_local_no_llamaparse"]
    else:
        llama_pages, logs = route_table_pages(input_path, start, end, manual_table_pages, detect_tables=True)
        llama_pages = [p for p in llama_pages if start <= p <= end]

    local_pages = [p for p in all_pages if p not in set(llama_pages)]
    page_blocks: dict[int, str] = {}

    # 1) Chạy local cho các trang văn bản thường.
    for group_start, group_end in group_contiguous_pages(local_pages):
        body, _metadata = local_body_for_range(input_path, output_path.parent, group_start, group_end, base_config=base_config)
        page_blocks.update(split_local_markdown_by_page(body))

    # 2) Chạy LlamaParse cho các trang bảng/lưu đồ thật.
    for group_start, group_end in group_contiguous_pages(llama_pages):
        llama_blocks = llama_body_for_range(
            input_path=input_path,
            page_start=group_start,
            page_end=group_end,
            llama_tier=llama_tier,
            export_tables_as_xlsx=export_tables_as_xlsx,
            preserve_spatial_text=preserve_spatial_text,
            disable_cache=disable_cache,
            aggressive_tables=aggressive_tables,
            repair_false_tables=repair_false_tables,
        )
        # Chạy lại lớp sửa lỗi chung/từ điển CTU cho output LlamaParse để thống nhất
        # với nhánh local OCR. Import lazy để tránh vòng import khi main gọi router.
        if base_config is not None:
            try:
                from main import chay_ba_lop_hau_xu_ly
                llama_blocks = {p: chay_ba_lop_hau_xu_ly(block, base_config) for p, block in llama_blocks.items()}
            except Exception:
                pass
        page_blocks.update(llama_blocks)

    # 3) Ghép đúng thứ tự trang, kèm log detector để dễ debug.
    header = build_table_safe_metadata(
        input_path=input_path,
        total_pages=total_pages,
        page_start=start,
        page_end=end,
        local_pages=local_pages,
        llama_pages=llama_pages,
        engine_mode=engine,
    )
    debug_log = "\n".join(f"<!-- layout_analyzer: {line} -->" for line in logs)
    ordered_blocks = [page_blocks.get(p, make_page_block(p, "[Không tạo được nội dung trang này]")) for p in all_pages]
    final_md = header + debug_log + "\n\n" + "\n\n---\n\n".join(clean_page_block(b) for b in ordered_blocks).strip() + "\n"
    final_md = postprocess_final_markdown(final_md)
    final_md = apply_metadata_to_markdown(
        final_md,
        md_path=output_path,
        source_file=input_path,
        language=getattr(base_config, "ngon_ngu_ocr", "vi"),
    )
    errors, warnings = validate_metadata_text(final_md)
    for error in errors:
        print(f"[METADATA ERROR] {output_path}: {error}")
    for warning in warnings:
        print(f"[METADATA WARN] {output_path}: {warning}")

    ghi_text_unicode(output_path, final_md)
    return output_path
