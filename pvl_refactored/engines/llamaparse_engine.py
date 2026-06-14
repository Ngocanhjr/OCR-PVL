"""
llamaparse_engine.py

Module tích hợp LlamaParse v2 vào pipeline OCR hiện có.
- Dùng khi PDF scan / bảng / biểu mẫu / layout phức tạp.
- Trả về Markdown có page marker để đưa tiếp qua clean/chunking/RAG.

Bản SAFE cập nhật:
- Mặc định KHÔNG bật aggressive_table_extraction để tránh biến văn bản thường thành bảng.
- Prompt ràng buộc rõ: chỉ tạo Markdown table khi trang thật sự có bảng/cell/đường kẻ.
- Có hậu xử lý loại bỏ một số bảng giả do LlamaParse tạo từ đoạn văn bản thường.

Cài đặt:
    pip install "llama-cloud>=2.1" python-dotenv

Thiết lập API key trên PowerShell:
    setx LLAMA_CLOUD_API_KEY "llx-..."
    # đóng/mở lại PowerShell sau khi setx
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from processing.table_form_postprocess import postprocess_final_markdown

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv_if_available() -> list[Path]:
    """
    Nạp API key từ file .env nếu có.

    Hàm này cố ý tìm .env ở 3 vị trí thường gặp:
    1. Thư mục chứa file source hiện tại.
    2. Thư mục đang chạy lệnh PowerShell/cmd.
    3. Thư mục cha của source, phòng khi người dùng chạy từ project root.

    Nếu chưa cài python-dotenv thì hàm không làm chương trình lỗi ngay;
    khi thiếu key, thông báo lỗi sẽ chỉ rõ cách cài.
    """
    loaded_paths: list[Path] = []
    candidates = [
        SOURCE_ROOT / ".env",
        Path.cwd() / ".env",
        SOURCE_ROOT.parent / ".env",
    ]

    try:
        from dotenv import load_dotenv
    except ImportError:
        return loaded_paths

    seen: set[Path] = set()
    for env_path in candidates:
        env_path = env_path.resolve()
        if env_path in seen:
            continue
        seen.add(env_path)
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            loaded_paths.append(env_path)

    return loaded_paths


Tier = Literal["fast", "cost_effective", "agentic", "agentic_plus"]
ChartMode = Literal["efficient", "agentic", "agentic_plus"]


@dataclass
class LlamaParseConfig:
    """Cấu hình parse cho LlamaParse v2."""

    tier: Tier = "agentic"
    version: str = "latest"
    language: str = "vi"

    # Chỉ parse một đoạn trang để tiết kiệm credits. LlamaParse v2 dùng page 1-based.
    page_start: Optional[int] = None
    page_end: Optional[int] = None

    # Bảng / hình / layout
    output_tables_as_markdown: bool = True
    merge_continued_tables: bool = True
    export_tables_as_xlsx: bool = False
    preserve_spatial_text: bool = False
    save_images: bool = False
    specialized_chart_parsing: Optional[ChartMode] = None

    # SAFE DEFAULT: False để tránh nhầm đoạn văn bản thẳng hàng thành bảng.
    # Chỉ bật True cho trang thật sự nhiều bảng/lưu đồ phức tạp.
    aggressive_table_extraction: bool = False

    # Nếu True, hậu xử lý sẽ cố chuyển các markdown table giả thành text thường.
    repair_false_tables: bool = True

    # Cache và custom prompt
    disable_cache: bool = False
    custom_prompt: Optional[str] = None

    # Timeout an toàn cho file nhiều trang
    base_timeout_seconds: int = 300
    extra_timeout_per_page_seconds: int = 30


def _validate_file(input_path: str | Path) -> Path:
    """Kiểm tra file input có tồn tại không."""
    path = Path(input_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {path}")
    if not path.is_file():
        raise ValueError(f"Đường dẫn không phải file: {path}")
    return path


def tao_llama_config(
    llama_tier: str = "agentic",
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
    export_tables_as_xlsx: bool = False,
    preserve_spatial_text: bool = False,
    disable_cache: bool = False,
    aggressive_tables: bool = False,
    repair_false_tables: bool = True,
) -> LlamaParseConfig:
    """Tạo LlamaParseConfig từ các tham số CLI phổ biến.

    Dùng thay cho việc khởi tạo LlamaParseConfig thủ công ở
    hybrid_page_router và hybrid_router - cùng args, cùng logic specialized_chart_parsing.
    """
    return LlamaParseConfig(
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


def _build_target_pages(page_start: Optional[int], page_end: Optional[int]) -> Optional[str]:
    """Tạo chuỗi page_ranges.target_pages cho LlamaParse v2, dùng page 1-based."""
    if page_start is None and page_end is None:
        return None

    start = page_start or 1
    end = page_end or start

    if start < 1 or end < 1:
        raise ValueError("LlamaParse v2 dùng số trang bắt đầu từ 1. page_start/page_end phải >= 1.")
    if end < start:
        raise ValueError("page_end phải >= page_start.")

    return str(start) if start == end else f"{start}-{end}"


def _default_ctu_prompt() -> str:
    """Prompt để LlamaParse giữ cấu trúc văn bản hành chính CTU và không tạo bảng giả."""
    return (
        "Đây là văn bản hành chính, quy định, quy trình, thủ tục hoặc biểu mẫu của Trường Đại học Cần Thơ. "
        "Hãy giữ đúng tiếng Việt có dấu, số hiệu văn bản, ngày tháng, đơn vị ban hành, tiêu đề, mục Chương/Điều/Khoản/Điểm, danh sách đánh số. "
        "Không tự tóm tắt nội dung. Xuất Markdown sạch để dùng cho RAG. "
        "QUY TẮC BẢNG RẤT QUAN TRỌNG: Chỉ tạo Markdown table khi trên trang thật sự có bảng rõ ràng, có đường kẻ/cell/cột/hàng hoặc header cột như Bước, Lưu đồ, Nội dung công việc, Người thực hiện, Thời gian, Ghi chú, TT, Nội dung vi phạm, Lần 1, Lần 2, Lần 3, Phân loại. "
        "Không được biến tiêu đề, mục 1/1.1/a/b/c, hoặc đoạn văn bản thường thành bảng. "
        "Nếu bảng kéo dài sang trang sau, hãy lặp lại header bảng ở đầu trang sau để Markdown không bị mất cột. "
        "Nếu bảng có tên bảng nằm phía trên các cột, hãy đặt tên bảng thành heading riêng trước bảng; không lặp tên bảng trong từng header cột. "
        "Header bảng chỉ giữ tên cột thật như Bước, Lưu đồ, Nội dung công việc, Người thực hiện, Thời gian thực hiện, Ghi chú, TT, Phân loại. "
        "QUY TẮC BIỂU MẪU: Với tờ khai/phiếu/mẫu có dòng chấm, checkbox, trường Họ tên, Ngày sinh, Giới tính, CCCD, Nơi cấp, hãy giữ đúng từng trường theo dạng danh sách hoặc bảng 2 cột 'Trường thông tin' và 'Giá trị/ghi chú'; không bỏ các ô checkbox. "
        "Nếu chỉ là văn bản bình thường, hãy giữ thành heading, paragraph và bullet list."
    )


def _build_parse_kwargs(file_id: str, cfg: LlamaParseConfig) -> dict:
    """Chuyển dataclass config thành kwargs cho client.parsing.parse()."""
    kwargs: dict = {
        "file_id": file_id,
        "tier": cfg.tier,
        "version": cfg.version,
        "expand": ["markdown", "text", "items", "metadata"],
        "processing_options": {
            "ocr_parameters": {"languages": [cfg.language]},
            "aggressive_table_extraction": cfg.aggressive_table_extraction,
        },
        "output_options": {
            "markdown": {
                "tables": {
                    "output_tables_as_markdown": cfg.output_tables_as_markdown,
                    "merge_continued_tables": cfg.merge_continued_tables,
                }
            },
            "extract_printed_page_number": True,
        },
        "processing_control": {
            "timeouts": {
                "base_in_seconds": cfg.base_timeout_seconds,
                "extra_time_per_page_in_seconds": cfg.extra_timeout_per_page_seconds,
            },
            "job_failure_conditions": {"allowed_page_failure_ratio": 0.05},
        },
        "disable_cache": cfg.disable_cache,
    }

    target_pages = _build_target_pages(cfg.page_start, cfg.page_end)
    if target_pages:
        kwargs["page_ranges"] = {"target_pages": target_pages}

    # Spatial text giúp giữ bố cục bằng khoảng trắng; hữu ích cho form/phiếu/bảng khó.
    if cfg.preserve_spatial_text:
        kwargs["output_options"]["spatial_text"] = {
            "preserve_layout_alignment_across_pages": True,
            "preserve_very_small_text": True,
            "do_not_unroll_columns": False,
        }

    if cfg.export_tables_as_xlsx:
        kwargs["output_options"]["tables_as_spreadsheet"] = {"enable": True}
        kwargs["expand"].append("xlsx_content_metadata")

    if cfg.save_images:
        kwargs["output_options"]["images_to_save"] = ["screenshot", "embedded", "layout"]
        kwargs["expand"].append("images_content_metadata")

    if cfg.specialized_chart_parsing:
        kwargs["processing_options"]["specialized_chart_parsing"] = cfg.specialized_chart_parsing

    # custom_prompt chỉ dùng cho cost_effective/agentic/agentic_plus, không dùng fast.
    prompt = cfg.custom_prompt or _default_ctu_prompt()
    if cfg.tier != "fast" and prompt:
        kwargs["agentic_options"] = {"custom_prompt": prompt}

    # Loại bỏ expand trùng lặp nhưng giữ thứ tự.
    kwargs["expand"] = list(dict.fromkeys(kwargs["expand"]))
    return kwargs


def _join_pages_as_markdown(result) -> str:
    """Ghép Markdown theo từng trang và thêm page marker cho citation trong RAG."""
    if not getattr(result, "markdown", None) or not getattr(result.markdown, "pages", None):
        raise RuntimeError("LlamaParse không trả về markdown.pages. Hãy kiểm tra expand=['markdown'] hoặc job parse.")

    blocks: list[str] = []
    for idx, page in enumerate(result.markdown.pages, start=1):
        page_no = getattr(page, "page", None) or getattr(page, "page_number", None) or idx
        page_md = getattr(page, "markdown", "") or ""
        page_md = page_md.strip()
        blocks.append(f"<!-- page: {page_no} -->\n\n{page_md}".strip())

    return "\n\n".join(blocks).strip() + "\n"


_TABLE_HEADER_HINTS = {
    "bước", "lưu đồ", "nội dung", "công việc", "người", "thực hiện", "thời gian",
    "ghi chú", "đơn vị", "phối hợp", "biểu mẫu", "minh chứng", "hồ sơ",
}


def _is_table_separator(line: str) -> bool:
    """Nhận diện dòng phân cách của markdown table."""
    return bool(re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$", line))


def _split_table_row(line: str) -> list[str]:
    """Tách cell của một dòng markdown table."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [re.sub(r"\s+", " ", c).strip(" *") for c in s.split("|")]


_TABLE_CELL_BREAK_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)


def _strip_cell_markup(value: str) -> str:
    """Bỏ HTML/Markdown markup khỏi ô bảng, chuẩn hóa whitespace. Dùng chung cho title key và title text."""
    value = _TABLE_CELL_BREAK_RE.sub(" ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[*_`#]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_title_key(value: str) -> str:
    """Chuẩn hóa tên bảng để so sánh lặp lại trong nhiều ô header."""
    return _strip_cell_markup(value).upper()


def _clean_table_title(value: str) -> str:
    """Làm sạch tên bảng trước khi đưa ra heading riêng bên trên bảng."""
    return _strip_cell_markup(value).strip(" |")


def _find_repeated_header_title(header_cells: list[str]) -> tuple[str | None, str | None]:
    """Tìm tên bảng bị LlamaParse lặp trong từng ô header.

    Ví dụ lỗi thường gặp:
        | TÊN BẢNG<br/>Bước | TÊN BẢNG<br/>Lưu đồ | ... |

    Hàm trả về (title_key, title_text) nếu phần trước <br/> lặp lại ở nhiều ô.
    """
    candidates: dict[str, tuple[str, int]] = {}
    for cell in header_cells:
        parts = _TABLE_CELL_BREAK_RE.split(cell, maxsplit=1)
        if len(parts) < 2:
            continue
        title_text = _clean_table_title(parts[0])
        title_key = _normalize_title_key(title_text)
        if len(title_key) < 12:
            continue
        old_text, count = candidates.get(title_key, (title_text, 0))
        candidates[title_key] = (old_text, count + 1)

    if not candidates:
        return None, None

    title_key, (title_text, count) = max(candidates.items(), key=lambda item: item[1][1])
    # Chỉ coi là lỗi nếu tên bảng lặp ở ít nhất 2 cột. Với bảng thật như trang 4 thường lặp ở toàn bộ cột.
    if count < 2:
        return None, None
    return title_key, title_text


def _strip_repeated_title_from_cell(cell: str, title_key: str) -> str:
    """Bỏ phần tên bảng lặp ở đầu ô header, giữ lại tên cột thật."""
    parts = _TABLE_CELL_BREAK_RE.split(cell, maxsplit=1)
    if len(parts) < 2:
        return cell.strip()
    first_key = _normalize_title_key(parts[0])
    if first_key == title_key:
        return parts[1].strip() or cell.strip()
    return cell.strip()


def _previous_lines_contain_title(out_lines: list[str], title_key: str, lookback: int = 6) -> bool:
    """Kiểm tra tên bảng đã xuất hiện ngay trước bảng chưa để tránh thêm heading trùng."""
    checked = 0
    for line in reversed(out_lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("<!--"):
            continue
        checked += 1
        if title_key and title_key in _normalize_title_key(stripped):
            return True
        if checked >= lookback:
            break
    return False


def normalize_repeated_table_titles(markdown: str) -> str:
    """Sửa lỗi tên bảng bị lặp trong từng cột header của Markdown table.

    Markdown chuẩn không hỗ trợ gộp cột (`colspan`). Vì vậy cách đúng cho RAG là:
    - đưa tên bảng thành một heading riêng phía trên bảng;
    - header của bảng chỉ giữ tên cột thật: Bước, Lưu đồ, Nội dung công việc,...

    Hàm này không đụng vào nội dung các dòng dữ liệu, chỉ sửa dòng header của bảng.
    """
    lines = markdown.split("\n")
    out: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        # Một bảng Markdown hợp lệ có dòng header ngay trước dòng separator.
        if "|" in line and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            header_cells = _split_table_row(line)
            title_key, title_text = _find_repeated_header_title(header_cells)
            if title_key and title_text:
                new_cells = [_strip_repeated_title_from_cell(c, title_key) for c in header_cells]
                # Bỏ cell rỗng ở hai đầu nếu có, nhưng giữ số cột thực tế.
                new_header = "| " + " | ".join(c or " " for c in new_cells) + " |"

                if not _previous_lines_contain_title(out, title_key):
                    if out and out[-1].strip():
                        out.append("")
                    out.append(f"## {title_text}")
                    out.append("")

                out.append(new_header)
                i += 1
                continue

        out.append(line)
        i += 1

    return "\n".join(out)


def _looks_like_false_table(table_lines: list[str]) -> bool:
    """
    Heuristic nhận diện bảng giả do OCR/parser tạo nhầm từ văn bản thường.

    Không chuyển các bảng thật nếu có header/cột rõ như Bước, Lưu đồ, Nội dung công việc...
    Chủ yếu bắt trường hợp 1-2 cột, nhiều cell rỗng, dòng dạng heading/mục văn bản.
    """
    data_rows = [ln for ln in table_lines if "|" in ln and not _is_table_separator(ln)]
    if not data_rows:
        return False

    rows = [_split_table_row(ln) for ln in data_rows]
    max_cols = max((len(r) for r in rows), default=0)
    all_text = " ".join(" ".join(r) for r in rows).lower()

    # Nếu có dấu hiệu bảng thật thì không động vào.
    if any(h in all_text for h in _TABLE_HEADER_HINTS):
        return False

    non_empty_cells = [c for r in rows for c in r if c]
    empty_cells = [c for r in rows for c in r if not c]
    empty_ratio = len(empty_cells) / max(sum(len(r) for r in rows), 1)

    first_cells = [r[0] for r in rows if r]
    section_like = sum(
        1 for c in first_cells
        if re.match(r"^(\d+(\.\d+)*\.?\s+|[a-zA-Zà-ỹ]\.|[IVXLCDM]+\.|I+\.|V+\.)", c.strip(), flags=re.I)
    )

    # Bảng giả thường rất ít cột, nhiều ô rỗng hoặc ô cột phải chỉ là 1-2 từ bị tách sai.
    short_right_cells = 0
    right_cells = []
    for r in rows:
        if len(r) > 1:
            right_cells.extend(r[1:])
    for c in right_cells:
        if c and len(c.split()) <= 2:
            short_right_cells += 1
    short_right_ratio = short_right_cells / max(len([c for c in right_cells if c]), 1)

    return (
        max_cols <= 2
        and (
            empty_ratio >= 0.35
            or section_like >= 1
            or short_right_ratio >= 0.7
        )
    )


def _table_to_plain_text(table_lines: list[str]) -> list[str]:
    """Chuyển bảng giả thành các dòng text thường bằng cách ghép cell không rỗng."""
    plain: list[str] = []
    for ln in table_lines:
        if _is_table_separator(ln):
            continue
        cells = [c for c in _split_table_row(ln) if c]
        if not cells:
            continue
        plain.append(" ".join(cells).strip())
    return plain


def repair_false_markdown_tables(text: str) -> str:
    """Loại bỏ các markdown table giả nhưng giữ bảng thật."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "|" not in line or line.strip().startswith("<!--"):
            out.append(line)
            i += 1
            continue

        block: list[str] = []
        j = i
        while j < len(lines) and ("|" in lines[j] or _is_table_separator(lines[j]) or not lines[j].strip()):
            if not lines[j].strip() and block:
                break
            if lines[j].strip():
                block.append(lines[j])
            j += 1

        if len(block) >= 2 and any(_is_table_separator(ln) for ln in block) and _looks_like_false_table(block):
            out.extend(_table_to_plain_text(block))
            i = j
        else:
            out.append(line)
            i += 1

    return "\n".join(out)


def normalize_llamaparse_markdown(markdown: str, repair_false_tables: bool = True) -> str:
    """Hậu xử lý nhẹ sau LlamaParse để hợp với pipeline CTU."""
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")

    # LlamaParse đôi khi biểu diễn tên bảng dạng cell gộp bằng cách lặp lại
    # tên bảng trong từng ô header. Markdown không hỗ trợ colspan nên chuyển
    # tên bảng thành heading riêng và chỉ giữ tên cột thật trong header.
    text = normalize_repeated_table_titles(text)

    if repair_false_tables:
        text = repair_false_markdown_tables(text)

    # Chuẩn hóa khoảng trắng nhưng không phá markdown table thật.
    lines: list[str] = []
    for line in text.split("\n"):
        if "|" in line and re.match(r"^\s*\|?.+\|", line):
            lines.append(line.rstrip())
        else:
            line = re.sub(r"[ \t]+", " ", line).strip()
            lines.append(line)

    text = "\n".join(lines)

    # Chuẩn hóa tiêu đề hành chính phổ biến nếu LlamaParse chưa gắn heading.
    heading_patterns = [
        r"^(CHƯƠNG\s+[IVXLCDM]+\b.*)$",
        r"^(Chương\s+[IVXLCDM]+\b.*)$",
        r"^(Điều\s+\d+\.?\s+.*)$",
        r"^(PHỤ LỤC\s+.*)$",
        r"^(QUYẾT ĐỊNH\b.*)$",
        r"^(QUY ĐỊNH\b.*)$",
        r"^(QUY TRÌNH\b.*)$",
    ]

    normalized_lines: list[str] = []
    in_table = False
    for line in text.split("\n"):
        stripped = line.strip()
        if "|" in stripped and re.match(r"^\|?.+\|", stripped):
            in_table = True
        elif stripped == "":
            in_table = False

        if not stripped or stripped.startswith("#") or stripped.startswith("<!-- page:") or in_table:
            normalized_lines.append(line)
            continue
        if any(re.match(p, stripped) for p in heading_patterns):
            normalized_lines.append(f"## {stripped}")
        else:
            normalized_lines.append(line)

    text = "\n".join(normalized_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = postprocess_final_markdown(text)
    return text.strip() + "\n"


def parse_with_llamaparse(input_path: str | Path, cfg: Optional[LlamaParseConfig] = None) -> str:
    """Upload file lên LlamaCloud, chạy LlamaParse và trả về Markdown."""
    cfg = cfg or LlamaParseConfig()
    file_path = _validate_file(input_path)

    loaded_env_paths = _load_dotenv_if_available()
    if not os.getenv("LLAMA_CLOUD_API_KEY"):
        searched_paths = [
            SOURCE_ROOT / ".env",
            Path.cwd() / ".env",
            SOURCE_ROOT.parent / ".env",
        ]
        searched = "; ".join(str(p.resolve()) for p in searched_paths)
        loaded = ", ".join(str(p) for p in loaded_env_paths) or "không có"
        raise EnvironmentError(
            "Thiếu LLAMA_CLOUD_API_KEY. "
            "Nếu dùng file .env, hãy đặt file .env cùng thư mục với main.py và ghi dòng: "
            "LLAMA_CLOUD_API_KEY=llx-API_KEY_CUA_BAN. "
            "Nếu chưa cài dotenv, chạy: python -m pip install python-dotenv. "
            "Hoặc set biến môi trường PowerShell: $env:LLAMA_CLOUD_API_KEY=\"llx-...\". "
            f"Đường dẫn .env đã tìm: {searched}. Đã nạp: {loaded}."
        )

    try:
        from llama_cloud import LlamaCloud
    except ImportError as exc:
        raise ImportError(
            "Chưa cài llama-cloud. Hãy chạy: pip install \"llama-cloud>=2.1\" python-dotenv"
        ) from exc

    client = LlamaCloud()
    uploaded_file = client.files.create(file=str(file_path), purpose="parse")
    parse_kwargs = _build_parse_kwargs(file_id=uploaded_file.id, cfg=cfg)

    result = client.parsing.parse(**parse_kwargs)
    markdown = _join_pages_as_markdown(result)
    return normalize_llamaparse_markdown(markdown, repair_false_tables=cfg.repair_false_tables)


def save_llamaparse_markdown(
    input_path: str | Path,
    output_path: str | Path,
    cfg: Optional[LlamaParseConfig] = None,
) -> Path:
    """Parse file bằng LlamaParse và lưu Markdown ra output_path."""
    from validation.apply_metadata import ap_dung_va_xac_thuc_metadata

    markdown = parse_with_llamaparse(input_path, cfg)
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    markdown = ap_dung_va_xac_thuc_metadata(markdown, out, input_path, ocr_status="done")
    out.write_text(markdown, encoding="utf-8")
    return out
