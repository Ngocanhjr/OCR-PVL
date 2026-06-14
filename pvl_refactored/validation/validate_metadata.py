from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from validation.apply_metadata import FIELD_ORDER, iter_markdown_files, is_empty, split_front_matter


ENUMS = {
    "collection_status": {"link_collected", "collected", "downloaded", "missing", "failed"},
    "ocr_status": {"not_started", "processing", "done", "failed", "need_review", "not_required"},
    "review_status": {"not_reviewed", "reviewing", "need_fix", "approved", "rejected"},
    "validity_status": {"unchecked", "valid", "expired", "replaced", "unknown"},
    "rag_status": {"not_indexed", "chunked", "embedded", "indexed", "published", "deactivated", "failed"},
    "document_type": {
        "noi_quy",
        "quy_trinh",
        "bieu_mau",
        "hoi_dap",
        "huong_dan",
        "huong_dan_metadata",
        "huong_dan_quan_tri",
        "huong_dan_theo_doi",
        "ghi_chu_nghien_cuu",
    },
    "file_type": {"pdf", "docx", "md", "html", "image", "xlsx", "csv", "url", "youtube"},
    "confidentiality": {"public", "internal", "restricted"},
    "citation_type": {"page", "section", "none"},
    "chunking_strategy": {"heading_aware_parent_child", "qa_based", "asset_based", "manual"},
}

AUTO_REQUIRED_FIELDS = {
    "document_id",
    "version_id",
    "collection_status",
    "ocr_status",
    "review_status",
    "rag_status",
    "source_file",
    "file_type",
    "language",
    "citation_type",
    "chunking_strategy",
    "created_at",
    "updated_at",
    "checksum",
}

HUMAN_REVIEW_FIELDS = {
    "title",
    "document_type",
    "domain",
    "department",
    "audience",
    "confidentiality",
}

OPTIONAL_HUMAN_FIELDS = {
    "code",
    "issued_date",
    "effective_date",
    "expiry_date",
    "version",
    "replaces",
    "replaced_by",
    "source_url",
    "accessed_date",
    "notes",
}

DATE_FIELDS = {"issued_date", "effective_date", "expiry_date", "accessed_date"}


def scalar(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    if value is None:
        return ""
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def validate_metadata_text(text: str) -> tuple[list[str], list[str]]:
    metadata, _body = split_front_matter(text)
    errors: list[str] = []
    warnings: list[str] = []

    if not metadata:
        return ["missing YAML front matter"], []

    for field in FIELD_ORDER:
        if field not in metadata:
            errors.append(f"missing field: {field}")

    for field in metadata:
        if field not in FIELD_ORDER:
            warnings.append(f"unknown field: {field}")

    for field in AUTO_REQUIRED_FIELDS:
        if field in metadata and is_empty(metadata.get(field)):
            errors.append(f"auto required field is empty: {field}")

    for field in HUMAN_REVIEW_FIELDS:
        if field in metadata and is_empty(metadata.get(field)):
            warnings.append(f"needs human review: {field} is empty")

    for field in OPTIONAL_HUMAN_FIELDS:
        if field in metadata and is_empty(metadata.get(field)):
            warnings.append(f"optional human field is empty: {field}")

    if "audience" in metadata and not is_empty(metadata.get("audience")):
        if not isinstance(metadata.get("audience"), list):
            errors.append("audience must be a list")
        elif any(not isinstance(item, str) or not item for item in metadata["audience"]):
            errors.append("audience must contain non-empty strings")

    if "is_latest" in metadata and not isinstance(metadata.get("is_latest"), bool):
        errors.append("is_latest must be true or false")

    for field, allowed in ENUMS.items():
        if field not in metadata or is_empty(metadata.get(field)):
            continue
        value = metadata.get(field)
        if not isinstance(value, str):
            errors.append(f"{field} must be a string enum")
        elif value not in allowed:
            errors.append(f"{field} has invalid enum: {value}")

    checksum = scalar(metadata, "checksum")
    if checksum and not re.fullmatch(r"[0-9a-fA-F]{32}", checksum):
        errors.append("checksum must be a 32-character MD5 hex string")

    for field in DATE_FIELDS:
        value = scalar(metadata, field)
        if value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            errors.append(f"{field} must use YYYY-MM-DD")

    if scalar(metadata, "rag_status") == "published":
        if scalar(metadata, "ocr_status") not in {"done", "not_required"}:
            errors.append("published document must have ocr_status done or not_required")
        if scalar(metadata, "review_status") != "approved":
            errors.append("published document must have review_status approved")
        if scalar(metadata, "validity_status") != "valid":
            errors.append("published document must have validity_status valid")
        if scalar(metadata, "confidentiality") != "public":
            errors.append("published document must have confidentiality public")

    return errors, warnings


def validate_one(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    return validate_metadata_text(text)


def print_result(path: Path, errors: list[str], warnings: list[str]) -> None:
    if errors:
        status = "ERROR"
    elif warnings:
        status = "WARN"
    else:
        status = "OK"

    print(f"[{status}] {path}")
    for item in errors:
        print(f"  error: {item}")
    for item in warnings:
        print(f"  warn: {item}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate canonical YAML metadata in Markdown files.")
    parser.add_argument("path", help="Markdown file or directory.")
    parser.add_argument("--recursive", "-r", action="store_true", help="Validate *.md recursively when path is a directory.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    target = Path(args.path)
    files = iter_markdown_files(target, args.recursive)
    if not files:
        print(f"[WARN] No Markdown files found: {target}")
        return 1

    total_errors = 0
    total_warnings = 0
    for path in files:
        errors, warnings = validate_one(path)
        print_result(path, errors, warnings)
        total_errors += len(errors)
        total_warnings += len(warnings)

    print(f"[DONE] files={len(files)} errors={total_errors} warnings={total_warnings}")
    if total_errors:
        return 1
    if args.strict and total_warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
