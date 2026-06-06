# CHANGES - Page Marker Cleanup

Bản này sửa lỗi page marker bị xuất thành heading Markdown `## Trang n`.

## Thay đổi chính

- Thêm `page_markers.py` để gom logic page marker vào một nơi.
- Output mới dùng chuẩn duy nhất: `<!-- page: n -->`.
- Không còn sinh `## Trang n` trong `main.py` và `hybrid_page_router.py`.
- `split_local_markdown_by_page()` vẫn đọc được output cũ có `## Trang n`.
- `table_form_postprocess.py` được cập nhật để tách trang theo `<!-- page: n -->`, không phụ thuộc vào heading H2.
- Hậu xử lý cuối tự normalize legacy heading `## Trang n` thành comment page marker trước khi ghi Markdown.

## Lý do

`## Trang n` là heading H2 nên dễ làm chunker Markdown hiểu nhầm thành tiêu đề nội dung. Với RAG, page marker nên là metadata phục vụ citation, không phải section heading.

## Chuẩn output mới

```md
<!-- page: 11 -->

<!-- extraction: pymupdf_text_no_table -->

Nội dung thật của trang...
```
