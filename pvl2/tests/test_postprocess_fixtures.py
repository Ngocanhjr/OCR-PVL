from __future__ import annotations

import unittest
from pathlib import Path

from processing.table_form_postprocess import postprocess_final_markdown


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "postprocess"


class PostprocessFixtureTest(unittest.TestCase):
    def test_postprocess_golden_fixtures(self) -> None:
        cases = sorted(path.parent for path in FIXTURE_ROOT.glob("*/input.md"))
        self.assertTrue(cases, f"No postprocess fixtures found under {FIXTURE_ROOT}")

        for case_dir in cases:
            with self.subTest(case=case_dir.name):
                input_text = (case_dir / "input.md").read_text(encoding="utf-8")
                expected = (case_dir / "expected.md").read_text(encoding="utf-8")
                self.assertEqual(postprocess_final_markdown(input_text), expected)


if __name__ == "__main__":
    unittest.main()
