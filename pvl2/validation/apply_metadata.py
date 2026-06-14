from __future__ import annotations

import argparse
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


OCR_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = OCR_ROOT.parent.parent
NLCS_ROOT = PROJECT_ROOT / "nlcs" if (PROJECT_ROOT / "nlcs").exists() else OCR_ROOT

FIELD_ORDER = [
    "document_id",
    "version_id",
    "title",
    "document_type",
    "domain",
    "department",
    "audience",
    "code",
    "issued_date",
    "effective_date",
    "expiry_date",
    "version",
    "is_latest",
    "validity_status",
    "replaces",
    "replaced_by",
    "collection_status",
    "ocr_status",
    "review_status",
    "rag_status",
    "source_url",
    "source_file",
    "file_type",
    "accessed_date",
    "language",
    "confidentiality",
    "citation_type",
    "chunking_strategy",
    "created_at",
    "updated_at",
    "checksum",
    "notes",
]

HUMAN_STRING_FIELDS = {
    "title",
    "document_type",
    "domain",
    "department",
    "code",
    "version",
    "source_url",
    "confidentiality",
}

HUMAN_NULL_FIELDS = {
    "issued_date",
    "effective_date",
    "expiry_date",
    "replaces",
    "replaced_by",
    "accessed_date",
    "notes",
}

SOURCE_EXTS = {
    ".pdf",
    ".doc",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
    ".xlsx",
    ".csv",
    ".html",
}

FILE_TYPE_BY_EXT = {
    ".pdf": "pdf",
    ".doc": "docx",
    ".docx": "docx",
    ".md": "md",
    ".html": "html",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "image",
    ".tiff": "image",
    ".bmp": "image",
    ".webp": "image",
    ".xlsx": "xlsx",
    ".csv": "csv",
}

OCR_METADATA_RE = re.compile(r"^\s*-\s*([^:]+):\s*(.*)\s*$")
RAW_OCR_REPORT_HEADER_RE = re.compile(
    r"\A\s*# PDF / Image Text Document\s*\n+## Metadata\s*\n+.*?^\s*## Extracted Text\s*$\s*",
    re.MULTILINE | re.DOTALL,
)
LAYOUT_ANALYZER_COMMENT_RE = re.compile(r"^\s*<!--\s*layout_analyzer:.*?-->\s*$\n?", re.MULTILINE)


@dataclass
class MetadataOptions:
    source_file: str | None = None
    ocr_status: str | None = None
    file_type: str | None = None
    language: str = "vi"
    document_type: str | None = None
    confidentiality: str | None = None
    overwrite_auto: bool = False


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", without_marks)


def slugify(value: str) -> str:
    text = strip_accents(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "untitled"


def normalize_name(value: str) -> str:
    return slugify(value).replace("-", "")


def is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            raw_yaml = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            return parse_simple_yaml(raw_yaml), body.lstrip("\r\n")

    return {}, text


def parse_simple_yaml(raw_yaml: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None

    for raw_line in raw_yaml.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        list_match = re.match(r"^\s*-\s*(.*)$", line)
        if list_match and current_key:
            if not isinstance(data.get(current_key), list):
                data[current_key] = []
            data[current_key].append(parse_scalar(list_match.group(1).strip()))
            continue

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(?:\s*(.*))?$", line)
        if not match:
            current_key = None
            continue

        key = match.group(1)
        value_text = match.group(2) if match.group(2) is not None else ""
        data[key] = parse_scalar(value_text.strip())
        current_key = key

    return data


def parse_scalar(value: str) -> Any:
    if value == "":
        return None
    if value == "[]":
        return []
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def yaml_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if text == "":
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_.-]+", text):
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def dump_front_matter(metadata: dict[str, Any]) -> str:
    lines = ["---"]
    for key in FIELD_ORDER:
        value = metadata.get(key)
        if isinstance(value, list):
            if value:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {yaml_scalar(item)}")
            else:
                lines.append(f"{key}: []")
        else:
            if value is None:
                lines.append(f"{key}:")
            else:
                lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def checksum_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_existing_path(value: str | None, md_path: Path) -> Path | None:
    if not value:
        return None

    raw = value.strip().strip("`")
    if not raw:
        return None

    candidates = [Path(raw)]
    if not Path(raw).is_absolute():
        candidates.extend([NLCS_ROOT / raw, md_path.parent / raw, Path.cwd() / raw])

    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def parse_ocr_metadata(body: str) -> dict[str, str]:
    result: dict[str, str] = {}
    in_metadata = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped == "## Metadata":
            in_metadata = True
            continue
        if in_metadata and stripped.startswith("## ") and stripped != "## Metadata":
            break
        if not in_metadata:
            continue

        match = OCR_METADATA_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip().lower()
        value = match.group(2).strip().strip("`")
        result[key] = value
    return result


def source_candidates_from_md(md_path: Path, ocr_meta: dict[str, str]) -> list[str]:
    stems = [md_path.stem]
    for suffix in ["_structured", "_rag_clean", "_clean", "_output"]:
        if stems[0].lower().endswith(suffix):
            stems.append(stems[0][: -len(suffix)])
    if ocr_meta.get("source name"):
        stems.append(Path(ocr_meta["source name"]).stem)
    if ocr_meta.get("source file"):
        stems.append(Path(ocr_meta["source file"]).stem)
    return list(dict.fromkeys(normalize_name(stem) for stem in stems if stem))


def find_source_file(md_path: Path, existing: dict[str, Any], ocr_meta: dict[str, str], cli_source: str | None) -> Path | None:
    for value in [cli_source, existing.get("source_file"), ocr_meta.get("source file")]:
        found = resolve_existing_path(str(value), md_path) if value else None
        if found:
            return found

    attachment_root = NLCS_ROOT / "02_Attachments"
    if not attachment_root.exists():
        return None

    wanted = set(source_candidates_from_md(md_path, ocr_meta))
    for candidate in attachment_root.rglob("*"):
        if candidate.is_file() and candidate.suffix.lower() in SOURCE_EXTS:
            if normalize_name(candidate.stem) in wanted:
                return candidate.resolve()
    return None


def path_for_metadata(path: Path) -> str:
    try:
        return path.resolve().relative_to(NLCS_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def detect_file_type(source_path: Path | None, existing: dict[str, Any], fallback: str | None) -> str:
    if fallback:
        return fallback
    if source_path:
        return FILE_TYPE_BY_EXT.get(source_path.suffix.lower(), source_path.suffix.lower().lstrip("."))
    existing_type = existing.get("file_type")
    return str(existing_type) if existing_type else ""


def generated_document_id(source_path: Path | None, md_path: Path) -> str:
    stem = source_path.stem if source_path else md_path.stem
    prefix_parts = ["ctu"]

    if source_path:
        parts = list(source_path.parts)
        lowered = [part.lower() for part in parts]
        if "pdfs" in lowered:
            index = lowered.index("pdfs")
            if index + 1 < len(parts):
                prefix_parts.append(slugify(parts[index + 1]))
        elif "docx" in lowered:
            index = lowered.index("docx")
            if index + 1 < len(parts):
                prefix_parts.append(slugify(parts[index + 1]))

    prefix_parts.append(slugify(stem))
    return "-".join(part for part in prefix_parts if part)


def generated_version_id(document_id: str, checksum: str) -> str:
    return f"{document_id}-{checksum[:12]}" if checksum else document_id


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if not is_empty(value):
            return value
    return None


def looks_like_ocr_output(body: str, ocr_meta: dict[str, str]) -> bool:
    if ocr_meta:
        return True
    return "## Extracted Text" in body or "<!-- page:" in body or "<!-- extraction:" in body


def strip_generated_ocr_report_noise(body: str) -> str:
    """Remove internal OCR report metadata/debug lines from the user-facing Markdown body."""

    cleaned = RAW_OCR_REPORT_HEADER_RE.sub("", body, count=1)
    cleaned = LAYOUT_ANALYZER_COMMENT_RE.sub("", cleaned)
    return cleaned.lstrip("\r\n")


def build_metadata(
    md_path: Path,
    existing: dict[str, Any],
    body: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    ocr_meta = parse_ocr_metadata(body)
    source_path = find_source_file(md_path, existing, ocr_meta, args.source_file)
    checksum = checksum_file(source_path) if source_path else first_non_empty(ocr_meta.get("checksum"), existing.get("checksum"), "")
    doc_id = first_non_empty(existing.get("document_id"), generated_document_id(source_path, md_path))
    old_checksum = existing.get("checksum") if isinstance(existing.get("checksum"), str) else ""
    current_version = existing.get("version_id")
    auto_old_version = generated_version_id(str(doc_id), old_checksum) if old_checksum else None
    if args.overwrite_auto or is_empty(current_version) or current_version == auto_old_version:
        version_id = generated_version_id(str(doc_id), str(checksum or ""))
    else:
        version_id = current_version

    ocr_status = first_non_empty(
        args.ocr_status,
        existing.get("ocr_status"),
        "done" if looks_like_ocr_output(body, ocr_meta) else "not_started",
    )

    metadata: dict[str, Any] = {field: None for field in FIELD_ORDER}

    for field in HUMAN_STRING_FIELDS:
        metadata[field] = existing.get(field, "")
    for field in HUMAN_NULL_FIELDS:
        metadata[field] = existing.get(field) if not is_empty(existing.get(field)) else None

    metadata.update(
        {
            "document_id": doc_id,
            "version_id": version_id,
            "audience": existing.get("audience") if not is_empty(existing.get("audience")) else ["student"],
            "is_latest": existing.get("is_latest") if isinstance(existing.get("is_latest"), bool) else False,
            "validity_status": first_non_empty(existing.get("validity_status"), "unchecked"),
            "collection_status": first_non_empty(existing.get("collection_status"), "collected"),
            "ocr_status": ocr_status,
            "review_status": first_non_empty(existing.get("review_status"), "not_reviewed"),
            "rag_status": first_non_empty(existing.get("rag_status"), "not_indexed"),
            "source_file": path_for_metadata(source_path) if source_path else first_non_empty(existing.get("source_file"), ocr_meta.get("source file"), ""),
            "file_type": detect_file_type(source_path, existing, args.file_type),
            "language": first_non_empty(args.language, existing.get("language"), "vi"),
            "citation_type": first_non_empty(existing.get("citation_type"), "page"),
            "chunking_strategy": first_non_empty(existing.get("chunking_strategy"), "heading_aware_parent_child"),
            "created_at": first_non_empty(existing.get("created_at"), now_iso()),
            "updated_at": now_iso(),
            "checksum": checksum,
        }
    )

    if args.document_type:
        metadata["document_type"] = args.document_type
    if args.confidentiality:
        metadata["confidentiality"] = args.confidentiality

    return metadata


def iter_markdown_files(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() == ".md" else []
    pattern = "**/*.md" if recursive else "*.md"
    return sorted(candidate for candidate in path.glob(pattern) if candidate.is_file())


def apply_to_file(md_path: Path, args: argparse.Namespace) -> bool:
    text = read_text(md_path)
    new_text = apply_metadata_to_markdown(
        text,
        md_path=md_path,
        source_file=args.source_file,
        ocr_status=args.ocr_status,
        file_type=args.file_type,
        language=args.language,
        document_type=args.document_type,
        confidentiality=args.confidentiality,
        overwrite_auto=args.overwrite_auto,
    )

    if args.dry_run:
        print(f"[DRY-RUN] {md_path}")
        return False

    md_path.write_text(new_text, encoding="utf-8", newline="\n")
    print(f"[OK] {md_path}")
    return True


def apply_metadata_to_markdown(
    markdown: str,
    md_path: str | Path,
    source_file: str | Path | None = None,
    ocr_status: str | None = None,
    file_type: str | None = None,
    language: str = "vi",
    document_type: str | None = None,
    confidentiality: str | None = None,
    overwrite_auto: bool = False,
) -> str:
    """Attach canonical YAML front matter to Markdown text.

    Only technical metadata is auto-filled. Fields that need human review stay
    empty unless the existing Markdown already has values or the caller passes
    explicit overrides.
    """

    existing, body = split_front_matter(markdown)
    options = MetadataOptions(
        source_file=str(source_file) if source_file else None,
        ocr_status=ocr_status,
        file_type=file_type,
        language=language,
        document_type=document_type,
        confidentiality=confidentiality,
        overwrite_auto=overwrite_auto,
    )
    metadata = build_metadata(Path(md_path), existing, body, options)
    body = strip_generated_ocr_report_noise(body)
    return dump_front_matter(metadata) + body


def apply_metadata_to_file(
    md_path: str | Path,
    source_file: str | Path | None = None,
    ocr_status: str | None = None,
    file_type: str | None = None,
    language: str = "vi",
    document_type: str | None = None,
    confidentiality: str | None = None,
    overwrite_auto: bool = False,
) -> Path:
    """Attach canonical YAML front matter to an existing Markdown file."""

    path = Path(md_path)
    updated = apply_metadata_to_markdown(
        read_text(path),
        md_path=path,
        source_file=source_file,
        ocr_status=ocr_status,
        file_type=file_type,
        language=language,
        document_type=document_type,
        confidentiality=confidentiality,
        overwrite_auto=overwrite_auto,
    )
    path.write_text(updated, encoding="utf-8", newline="\n")
    return path


def ap_dung_va_xac_thuc_metadata(
    markdown: str,
    output_path: str | Path,
    source_file: str | Path | None = None,
    language: str = "vi",
    **kw,
) -> str:
    """Gắn YAML front matter, xác thực và in lỗi/cảnh báo ra console.

    Dùng chung ở main.py, hybrid_page_router, hybrid_router và llamaparse_engine
    để tránh lặp pattern apply → validate → print ở 4 chỗ.
    Import validate_metadata_text cục bộ để tránh circular import.
    """
    from validation.validate_metadata import validate_metadata_text

    md = apply_metadata_to_markdown(
        markdown, md_path=output_path, source_file=source_file,
        language=language, **kw,
    )
    errors, warnings = validate_metadata_text(md)
    for e in errors:
        print(f"[METADATA ERROR] {output_path}: {e}")
    for w in warnings:
        print(f"[METADATA WARN] {output_path}: {w}")
    return md


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Attach canonical YAML metadata to Markdown files.")
    parser.add_argument("path", help="Markdown file or directory.")
    parser.add_argument("--recursive", "-r", action="store_true", help="Process *.md recursively when path is a directory.")
    parser.add_argument("--source-file", help="Original source file used for checksum/source_file.")
    parser.add_argument("--ocr-status", choices=["not_started", "processing", "done", "failed", "need_review", "not_required"])
    parser.add_argument("--file-type", choices=["pdf", "docx", "md", "html", "image", "xlsx", "csv", "url", "youtube"])
    parser.add_argument("--language", default="vi")
    parser.add_argument("--document-type", help="Optional human-reviewed document_type override.")
    parser.add_argument("--confidentiality", choices=["public", "internal", "restricted"], help="Optional human-reviewed confidentiality override.")
    parser.add_argument("--overwrite-auto", action="store_true", help="Refresh generated version_id and auto fields where possible.")
    parser.add_argument("--dry-run", action="store_true", help="Show files that would be changed without writing.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    target = Path(args.path)
    files = iter_markdown_files(target, args.recursive)
    if not files:
        print(f"[WARN] No Markdown files found: {target}")
        return 1

    changed = 0
    for md_path in files:
        changed += int(apply_to_file(md_path, args))

    print(f"[DONE] processed={len(files)} changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
