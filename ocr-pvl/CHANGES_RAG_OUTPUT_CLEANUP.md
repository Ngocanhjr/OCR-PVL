# Cập nhật RAG output cleanup

Bản này bổ sung lớp hậu xử lý nhẹ sau OCR/LlamaParse để output Markdown phù hợp hơn cho RAG.

## Lý do cập nhật

Khi so sánh output `QuyTrinh4-Congtacsinhvien.md` từ OCR_PVL với output LlamaParse web, OCR_PVL đã tốt hơn cho RAG vì có metadata, page marker `<!-- page: n -->` và bảng Markdown dễ chunk. Tuy nhiên output vẫn còn một số artifact nhỏ từ LlamaParse/API:

- Mục lục có dot leader bị đổi thành `________`.
- Một số ký hiệu flowchart thành LaTeX như `$\rightarrow$`.
- Dấu `*` trong bảng bị escape quá mức như `\\\* Học kỳ 1`.
- Một vài lỗi dính chữ phổ biến như `SVtrình`, `số16/`, `PhòngCTSV`.
- Một số dòng mục con `**1.1 ...**` chưa thành heading, làm chunker khó tách theo cấu trúc nghiệp vụ.

## File đã sửa/thêm

- `table_form_postprocess.py`
  - Thêm `normalize_toc_dot_leaders()`.
  - Thêm `normalize_llamaparse_rag_artifacts()`.
  - Thêm `normalize_ctu_markdown_headings()`.
  - Gọi các bước này trong `postprocess_final_markdown()`.
- `normalize_existing_markdown.py`
  - Script làm sạch lại file Markdown đã OCR/parse mà không cần chạy OCR lại.

## Cách dùng nhanh

```powershell
python normalize_existing_markdown.py QuyTrinh4-Congtacsinhvien.md -o QuyTrinh4-Congtacsinhvien_rag_clean.md
```

## Khuyến nghị cho tài liệu CTU

- Với tài liệu có lưu đồ/bảng nhiều trang: dùng `--engine llamaparse` hoặc `--engine auto-page --table-pages ...`.
- Với output cuối đưa vào RAG: luôn giữ page marker dạng `<!-- page: n -->`.
- Không dùng `## Trang n` vì dễ làm chunker hiểu nhầm là heading nghiệp vụ.
