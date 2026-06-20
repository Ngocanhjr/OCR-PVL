from __future__ import annotations

import unittest

from pipeline.quality import assess_table_page
from pipeline.retry_policy import TableRetryPolicy, should_retry_table_group


class TableQualityTest(unittest.TestCase):
    def test_good_table_scores_ok(self) -> None:
        markdown = (
            "| Bước | Lưu đồ | Nội dung công việc | Người thực hiện | Thời gian |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1 | Thông báo triển khai | Phát hành thông báo. | Phòng CTSV | 01 ngày |\n"
            "| 2 | SV tự đánh giá | Sinh viên tự đánh giá. | Sinh viên | 07 ngày |\n"
        )

        result = assess_table_page(markdown, page=4)

        self.assertGreaterEqual(result.score, 0.86)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.issues, [])

    def test_truncated_table_cell_lowers_score(self) -> None:
        markdown = (
            "| Bước | Lưu đồ | Nội dung công việc | Người thực hiện | Thời gian |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1 | Tiếp nhận và phản hồi thông | Bổ sung hồ sơ. | Sinh viên | 07 ngày |\n"
            "| 2 | Kiểm; | Rà soát hồ sơ. | Phòng CTSV | 03 ngày |\n"
        )

        result = assess_table_page(markdown, page=6)

        self.assertLess(result.score, 0.86)
        self.assertEqual(result.status, "needs_review")
        self.assertIn("table_1_possible_truncated_cells", result.issues)

    def test_retry_policy_escalates_low_quality_table(self) -> None:
        markdown = (
            "| Bước | Lưu đồ | Nội dung công việc | Người thực hiện | Thời gian |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1 | Kiểm; | Rà soát hồ sơ. | Phòng CTSV | 03 ngày |\n"
        )
        assessment = assess_table_page(markdown, page=6)

        should_retry = should_retry_table_group(
            {6: assessment},
            current_tier="agentic",
            current_spatial=False,
            current_aggressive_tables=False,
            policy=TableRetryPolicy(),
        )

        self.assertTrue(should_retry)


if __name__ == "__main__":
    unittest.main()
