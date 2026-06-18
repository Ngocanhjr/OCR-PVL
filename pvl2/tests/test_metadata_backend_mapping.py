from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "chatbot" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.documents import DocumentMetadata
from validation.apply_metadata import apply_metadata_to_markdown, split_front_matter
from validation.validate_metadata import validate_metadata_text


class MetadataBackendMappingTest(unittest.TestCase):
    def test_generated_metadata_passes_backend_document_schema(self) -> None:
        source = PROJECT_ROOT / "nlcs" / "03_Templates" / "Template_Metadata_Field_Guide.md"
        output = PROJECT_ROOT / "nlcs" / "01_Dataset" / "metadata_sample.md"

        markdown = apply_metadata_to_markdown(
            "<!-- page: 1 -->\n\n# Sample\n",
            md_path=output,
            source_file=source,
        )
        metadata, _body = split_front_matter(markdown)
        errors, _warnings = validate_metadata_text(markdown)

        self.assertEqual(errors, [])
        document = DocumentMetadata(**metadata)
        self.assertEqual(document.document_key, metadata["document_key"])
        self.assertEqual(document.version_key, metadata["version_key"])
        self.assertEqual(document.document_type, "unknown")
        self.assertEqual(document.source_file, source.name)
        self.assertEqual(document.source_path, "03_Templates/Template_Metadata_Field_Guide.md")

    def test_legacy_id_fields_are_upgraded_to_backend_keys(self) -> None:
        legacy = """---
document_id: ctu-legacy-doc
version_id: ctu-legacy-doc-v1
version: "2024"
document_type: huong_dan_metadata
citation_type: none
notes:
---

<!-- page: 1 -->

# Legacy
"""

        markdown = apply_metadata_to_markdown(legacy, md_path="legacy.md")
        metadata, _body = split_front_matter(markdown)

        self.assertEqual(metadata["document_key"], "ctu-legacy-doc")
        self.assertEqual(metadata["version_key"], "ctu-legacy-doc-v1")
        self.assertEqual(metadata["version_label"], "2024")
        self.assertEqual(metadata["document_type"], "unknown")
        self.assertEqual(metadata["citation_type"], "paragraph")
        self.assertNotIn("document_id", metadata)
        self.assertNotIn("version_id", metadata)
        DocumentMetadata(**metadata)


if __name__ == "__main__":
    unittest.main()
