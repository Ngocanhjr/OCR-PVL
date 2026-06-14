# OCR_PVL Pipeline Notes

This document describes the current behavior of `ocr-pvl`. It is documentation only;
it does not define a new architecture.

## Entry Point

The supported entry point is:

```powershell
python main.py <input_path> -o <output_path>
```

`main.py` owns argument parsing, file discovery, output path resolution, and dispatch
to the current OCR/parser routes.

## Current Routing Behavior

### PDF

PDF inputs from the CLI go through `hybrid_page_router.run_table_safe_pdf()`.

```text
PDF
-> count pages with PyMuPDF
-> choose requested page range
-> detect table/form pages unless --table-pages is supplied
-> process non-table pages with local pipeline
-> process table/form pages with LlamaParse
-> merge page blocks in numeric page order
-> postprocess Markdown
-> attach YAML metadata
-> write .md output
```

The local PDF path intentionally uses PyMuPDF text extraction only for text pages.
It does not use PyMuPDF table extraction.

### Image

Image inputs use local PaddleOCR/VietOCR by default.

If `--engine llamaparse` is used, images are sent through
`hybrid_router.run_document_parse()`.

### DOCX/PPTX/XLSX/CSV/HTML

These formats are only discovered by the CLI when `--engine llamaparse` is used.
They are sent through `hybrid_router.run_document_parse()`.

## Page Marker Contract

RAG page markers must remain HTML comments:

```md
<!-- page: 1 -->
<!-- page: 2 -->
```

They must not be converted into Markdown headings such as:

```md
## Trang 1
```

`processing/page_markers.py` still accepts legacy `## Trang n` headings and
normalizes them to the canonical comment format before final output.

## Table Handling Contract

Current table behavior is preserved:

- PDF table/form page detection is implemented in `pipeline/document_page_analyzer.py`.
- Page routing is implemented in `pipeline/hybrid_page_router.py`.
- Document-level fallback routing is implemented in `pipeline/hybrid_router.py`.
- LlamaParse is used for detected or manually selected table/form pages.
- `--table-pages` overrides automatic detection for selected pages.
- `--aggressive-tables` is opt-in and should only be used when the page is known to
  contain complex tables or flowcharts.

Do not change table detection thresholds, LlamaParse routing, or Markdown table
postprocessing without explicit approval.

## Text Layer Quality

`processing/text_layer_quality.py` is the single source for detecting bad PDF
text layers. It is kept independent from PaddleOCR/VietOCR imports so text PDFs
can be handled without initializing heavy OCR dependencies.

## Metadata Output

Canonical metadata is attached as YAML front matter through
`apply_metadata_to_markdown()` in `validation/apply_metadata.py`.

## Safe Refactor Boundary

Safe changes:

- Add tests for existing behavior.
- Improve documentation.
- Remove unused imports with project-wide proof.
- Clarify CLI help or error messages without changing behavior.

Needs approval:

- Changing OCR engine parameters.
- Changing page marker format.
- Changing Markdown cleaner rules.
- Changing table detection/routing.
- Moving more files across package boundaries.
- Changing CLI exit codes or accepted engine names.
