# Thay đổi đã sửa

## 1. Tự mở rộng trang bảng liền kề

Khi detector chỉ bắt được một trang bảng ở giữa, hệ thống sẽ tự kiểm tra trang liền trước/liền sau. Nếu các trang đó có nhiều vector line hoặc raster line score đủ cao, chúng sẽ được đưa sang LlamaParse chung.

Ví dụ file `Noi quy KTX nam 2016.pdf`:

- Trước sửa: `LlamaParse table pages: [5]`
- Sau sửa: `LlamaParse table pages: [4, 5, 6]`

Các hàm đã thêm/sửa:

- `document_page_analyzer.is_table_continuation_signal()`
- `document_page_analyzer.table_pages_from_signals(..., expand_contiguous_tables=True)`
- `hybrid_page_router.route_table_pages()` có log `expanded_table_pages` để dễ debug.

## 2. Giảm lỗi nhận nhầm list số thành heading

Các dòng kiểu sau không còn bị chuyển thành heading Markdown:

```md
7. Cho phép SV sử dụng các thiết bị điện:
2. Nghiêm cấm các hành vi sau:
```

Các dòng tiêu đề thật vẫn được giữ, ví dụ:

```md
1. Cơ sở thực hiện
1. Mục đích:
2.1 Thành phần hồ sơ
I. LƯU ĐỒ
```

Các hàm đã thêm/sửa:

- `markdown_layout.la_marker_heading_manh()`
- `markdown_layout.cap_heading_theo_marker()`

## Cách kiểm tra nhanh

Chạy lại file KTX bằng engine auto-page:

```powershell
python main.py "D:\Code\CTU_Student_Service\Dataset\02_Attachments\PDFs\CTSV\Noi quy KTX nam 2016.pdf" --engine auto-page
```

Trong đầu file `.md` output, kiểm tra dòng:

```md
- LlamaParse table pages: [4, 5, 6]
```
