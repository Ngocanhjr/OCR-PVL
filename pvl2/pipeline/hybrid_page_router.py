"""
hybrid_page_router.py

Router cấp trang cho PDF:
- Trang văn bản thường: dùng pipeline local TableSafe (PyMuPDF text-only hoặc Paddle+VietOCR).
- Trang có bảng/lưu đồ thật: dùng LlamaParse để tạo Markdown table/layout.

Phân ranh với `hybrid_router.py`:
- File PDF từ CLI `main.py` dùng `run_table_safe_pdf()` trong module này.
- Ảnh và tài liệu không phải PDF khi cần LlamaParse dùng `hybrid_router.run_document_parse()`.

Điểm quan trọng:
- Không dùng PyMuPDF để tạo bảng.
- Không gọi LlamaParse cho trang văn bản thường, tránh sinh bảng giả và tiết kiệm credits.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from config import ghi_text_unicode, tao_thu_muc_can_thiet
from pipeline.quality import assess_table_pages, assessments_to_report
from pipeline.retry_policy import TableRetryPolicy, should_retry_table_group
from engines.llamaparse_engine import parse_with_llamaparse
from processing.table_form_postprocess import postprocess_final_markdown
from validation.apply_metadata import ap_dung_va_xac_thuc_metadata
from processing.page_markers import (
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


def group_contiguous_pages(pages: Iterable[int]) -> list[tuple[int, int]]:
    """Group 1-based page numbers into contiguous ranges without importing PyMuPDF."""
    sorted_pages = sorted(set(int(p) for p in pages))
    if not sorted_pages:
        return []

    groups: list[tuple[int, int]] = []
    start = prev = sorted_pages[0]
    for page in sorted_pages[1:]:
        if page == prev + 1:
            prev = page
        else:
            groups.append((start, prev))
            start = prev = page
    groups.append((start, prev))
    return groups





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
    """Chạy pipeline local TableSafe cho một khoảng trang PDF."""
    from main import xu_ly_pdf
    from config import cau_hinh_cho_thu_muc

    cfg = cau_hinh_cho_thu_muc(
        Path(output_dir),
        nguon=base_config,
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
    """Gọi LlamaParse cho một khoảng trang có bảng/lưu đồ và trả về dict page→markdown."""
    from engines.llamaparse_engine import tao_llama_config

    expected_pages = list(range(page_start, page_end + 1))
    cfg = tao_llama_config(
        llama_tier=llama_tier, page_start=page_start, page_end=page_end,
        export_tables_as_xlsx=export_tables_as_xlsx, preserve_spatial_text=preserve_spatial_text,
        disable_cache=disable_cache, aggressive_tables=aggressive_tables,
        repair_false_tables=repair_false_tables,
    )
    markdown = parse_with_llamaparse(input_path, cfg)
    return split_llama_markdown_by_page(markdown, expected_pages)


def _postprocess_llama_blocks(blocks: dict[int, str], base_config=None) -> dict[int, str]:
    """Apply the same lightweight normalization to LlamaParse blocks as local OCR."""
    if base_config is None:
        return blocks

    try:
        from main import chay_ba_lop_hau_xu_ly
        return {page: chay_ba_lop_hau_xu_ly(block, base_config) for page, block in blocks.items()}
    except Exception:
        return blocks


def _select_better_table_blocks(
    initial_blocks: dict[int, str],
    retry_blocks: dict[int, str],
    initial_assessments,
    retry_assessments,
    policy: TableRetryPolicy,
) -> tuple[dict[int, str], dict[int, str]]:
    """Pick the better block per page by quality score."""
    selected_blocks = dict(initial_blocks)
    selected_sources: dict[int, str] = {}
    for page, initial in initial_assessments.items():
        retry = retry_assessments.get(page)
        if retry and retry.score >= initial.score + policy.min_improvement:
            selected_blocks[page] = retry_blocks.get(page, initial_blocks.get(page, ""))
            selected_sources[page] = "retry"
        else:
            selected_sources[page] = "initial"
    return selected_blocks, selected_sources


def _write_quality_report(output_path: Path, report: dict) -> None:
    """Write sidecar parser quality report next to the Markdown output."""
    report_path = output_path.with_name(f"{output_path.stem}.ocr_quality_report.json")
    ghi_text_unicode(report_path, json.dumps(report, ensure_ascii=False, indent=2))



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

    from pipeline.document_page_analyzer import analyze_pdf_pages, table_pages_from_signals

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
    table_quality_retry: bool = True,
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
    quality_policy = TableRetryPolicy(enabled=table_quality_retry)
    quality_groups: list[dict] = []

    # 1) Chạy local cho các trang văn bản thường.
    for group_start, group_end in group_contiguous_pages(local_pages):
        body, _metadata = local_body_for_range(input_path, output_path.parent, group_start, group_end, base_config=base_config)
        page_blocks.update(split_markdown_by_page(body))

    # 2) Chạy LlamaParse cho các trang bảng/lưu đồ thật.
    for group_start, group_end in group_contiguous_pages(llama_pages):
        expected_pages = list(range(group_start, group_end + 1))
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
        llama_blocks = _postprocess_llama_blocks(llama_blocks, base_config)

        # Quality gate is designed for auto-routed/manual table pages. When the
        # user explicitly runs engine=llamaparse for every page, do not assume
        # every page is a table.
        should_quality_check = engine != "llamaparse"
        selected_sources = {page: "initial" for page in expected_pages}
        initial_assessments = assess_table_pages(llama_blocks, expected_pages, min_score=quality_policy.min_score) if should_quality_check else {}
        attempts: list[dict] = []
        if should_quality_check:
            attempts.append({
                "name": "initial",
                "tier": llama_tier,
                "spatial": preserve_spatial_text,
                "aggressive_tables": aggressive_tables,
                "assessments": assessments_to_report(initial_assessments),
            })

        if should_quality_check and should_retry_table_group(
            initial_assessments,
            current_tier=llama_tier,
            current_spatial=preserve_spatial_text,
            current_aggressive_tables=aggressive_tables,
            policy=quality_policy,
        ):
            retry_blocks = llama_body_for_range(
                input_path=input_path,
                page_start=group_start,
                page_end=group_end,
                llama_tier=quality_policy.retry_tier,
                export_tables_as_xlsx=export_tables_as_xlsx,
                preserve_spatial_text=quality_policy.retry_spatial,
                disable_cache=disable_cache or quality_policy.retry_disable_cache,
                aggressive_tables=quality_policy.retry_aggressive_tables,
                repair_false_tables=repair_false_tables,
            )
            retry_blocks = _postprocess_llama_blocks(retry_blocks, base_config)
            retry_assessments = assess_table_pages(retry_blocks, expected_pages, min_score=quality_policy.min_score)
            attempts.append({
                "name": "retry",
                "tier": quality_policy.retry_tier,
                "spatial": quality_policy.retry_spatial,
                "aggressive_tables": quality_policy.retry_aggressive_tables,
                "assessments": assessments_to_report(retry_assessments),
            })
            llama_blocks, selected_sources = _select_better_table_blocks(
                llama_blocks,
                retry_blocks,
                initial_assessments,
                retry_assessments,
                quality_policy,
            )

        if should_quality_check:
            final_assessments = assess_table_pages(llama_blocks, expected_pages, min_score=quality_policy.min_score)
            quality_groups.append({
                "pages": expected_pages,
                "engine": "llamaparse",
                "attempts": attempts,
                "selected": {str(page): selected_sources.get(page, "initial") for page in expected_pages},
                "final_assessments": assessments_to_report(final_assessments),
                "final_status": "needs_review" if any(a.score < quality_policy.min_score for a in final_assessments.values()) else "ok",
            })

        page_blocks.update(llama_blocks)

    # 3) Ghép đúng thứ tự trang.
    ordered_blocks = [page_blocks.get(p, make_page_block(p, "[Không tạo được nội dung trang này]")) for p in all_pages]
    final_md = "\n\n---\n\n".join(clean_page_block(b) for b in ordered_blocks).strip() + "\n"
    final_md = postprocess_final_markdown(final_md)
    final_md = ap_dung_va_xac_thuc_metadata(
        final_md, output_path, input_path,
        language=getattr(base_config, "ngon_ngu_ocr", "vi"),
    )
    ghi_text_unicode(output_path, final_md)
    if quality_groups or logs:
        _write_quality_report(output_path, {
            "source_file": str(input_path),
            "output_file": str(output_path),
            "engine": engine,
            "page_start": start,
            "page_end": end,
            "llama_pages": llama_pages,
            "local_pages": local_pages,
            "routing_logs": logs,
            "table_quality_policy": {
                "enabled": quality_policy.enabled,
                "min_score": quality_policy.min_score,
                "retry_tier": quality_policy.retry_tier,
                "retry_spatial": quality_policy.retry_spatial,
                "retry_aggressive_tables": quality_policy.retry_aggressive_tables,
            },
            "table_quality_groups": quality_groups,
        })
    return output_path
