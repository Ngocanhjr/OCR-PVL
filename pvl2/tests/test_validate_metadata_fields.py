from __future__ import annotations

import sys
import unittest
from pathlib import Path


OCR_ROOT = Path(__file__).resolve().parents[1]
if str(OCR_ROOT) not in sys.path:
    sys.path.insert(0, str(OCR_ROOT))

from validation.validate_metadata import validate_metadata_text


class ValidateMetadataFieldsTest(unittest.TestCase):
    def test_core_metadata_fields_match_frontmatter_contract(self) -> None:
        markdown = """---
document_key: test-doc
version_key: test-doc-v1
title: "Test Document"
document_type: quy_trinh
domain: test
department: PDT
audience:
  - student
version_label: v1
version_role: base
is_latest: true
source_file: test.md
source_path: test.md
canonical_markdown_path: test.md
file_type: md
language: vi
citation_type: page
checksum: 0123456789abcdef0123456789abcdef
collection_status: collected
ocr_status: done
review_status: approved
validity_status: valid
rag_status: published
---

# Test
"""

        errors, warnings = validate_metadata_text(markdown)

        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
