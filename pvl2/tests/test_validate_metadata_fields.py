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

    def test_version_relationship_rules_match_backend_schema(self) -> None:
        cases = [
            (
                "validity_status: replaced\nversion_role: base",
                "replaced document requires replaced_by",
            ),
            (
                "validity_status: valid\nversion_role: replacement",
                "replacement version requires replaces",
            ),
            (
                "validity_status: valid\nversion_role: amendment",
                "amendment version requires amends",
            ),
            (
                "validity_status: valid\nversion_role: supplement",
                "supplement version requires supplements",
            ),
        ]

        for relation_metadata, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                markdown = f"""---
document_key: test-doc
version_key: test-doc-v1
title: "Test Document"
document_type: quy_trinh
domain: test
department: PDT
audience:
  - student
version_label: v1
{relation_metadata}
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
rag_status: not_indexed
---

# Test
"""

                errors, _warnings = validate_metadata_text(markdown)

                self.assertIn(expected_error, errors)


if __name__ == "__main__":
    unittest.main()
