from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from main import la_output_file_md, tao_output_path, tao_parser, tim_file_cli


class CliContractTest(unittest.TestCase):
    def test_parser_accepts_current_default_engine_and_output_file(self) -> None:
        args = tao_parser().parse_args(["input.pdf", "-o", "output.md", "--engine", "auto-page"])

        self.assertEqual(args.path, "input.pdf")
        self.assertEqual(args.output, "output.md")
        self.assertEqual(args.engine, "auto-page")

    def test_output_file_detection(self) -> None:
        self.assertTrue(la_output_file_md("result.md"))
        self.assertFalse(la_output_file_md("output"))

    def test_output_path_uses_file_when_md_is_given(self) -> None:
        output = tao_output_path(Path("input.pdf"), "custom.md")

        self.assertEqual(output, Path("custom.md"))

    def test_output_path_uses_structured_name_when_directory_is_given(self) -> None:
        output = tao_output_path(Path("Tài liệu mẫu.pdf"), "output")

        self.assertEqual(output, Path("output") / "Tài_liệu_mẫu_structured.md")

    def test_file_discovery_supports_single_file_and_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "a.pdf"
            image = root / "b.png"
            ignored = root / "c.txt"
            pdf.write_bytes(b"%PDF")
            image.write_bytes(b"png")
            ignored.write_text("skip", encoding="utf-8")

            self.assertEqual(tim_file_cli(pdf, "local"), [pdf])
            self.assertEqual(tim_file_cli(ignored, "local"), [])
            self.assertEqual(tim_file_cli(root, "local"), [pdf, image])


if __name__ == "__main__":
    unittest.main()
