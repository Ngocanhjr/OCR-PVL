# CHANGES - General OCR / Table / Form Fixes

Bản này sửa theo hướng **rule chung**, không hardcode riêng cho một file.

## 1. Từ thường gặp và lỗi OCR phổ biến

Cập nhật `common_fix.py` và `ctu_terms.py`:

- Sửa lỗi phổ biến trong văn bản pháp lý/hành chính:
  - `tin dụng` -> `tín dụng`
  - `đề giải ngân vôn vay` -> `để giải ngân vốn vay`
  - `kỳ han` -> `kỳ hạn`
  - `nghiện cứu sinh` -> `nghiên cứu sinh`
  - `thạc sỹ` -> `thạc sĩ`
  - `đóng dầu` -> `đóng dấu`
- Chuẩn hóa tên cơ quan:
  - `Ngân hàng Chính sách xã hội`
  - `Bộ Tài chính`
  - `Bộ Giáo dục và Đào tạo`
  - `Ngân hàng Nhà nước Việt Nam`
- Sửa một số lỗi tiêu đề biểu mẫu thường gặp:
  - `NGÂN JANG CHÍNH SÁCH XÃ HỘI` -> `NGÂN HÀNG CHÍNH SÁCH XÃ HỘI`
  - lỗi tiêu đề `MẪU TỜ KHAI THÔNG TIN...`
- Tự xóa watermark scan:
  - `Scanned with cs`
  - `CamScanner`

## 2. Nhận diện bảng/form tốt hơn

Cập nhật `document_page_analyzer.py`:

- Không chỉ dùng tổng số line raster nữa, vì dễ nhầm trang văn bản thường thành bảng.
- Tách riêng:
  - `raster_table_score`
  - `raster_form_score`
  - số đường ngang `h`
  - số đường dọc `v`
- Bảng thật cần cả dấu hiệu ngang và dọc, giúp tránh lỗi trang văn bản thường bị đưa qua LlamaParse.
- Thêm `likely_form` để nhận diện biểu mẫu/tờ khai khi có đủ dấu hiệu.

## 3. Hậu xử lý bảng và biểu mẫu

Thêm file mới `table_form_postprocess.py`:

- Sửa bảng Markdown bị mất header.
- Sửa lỗi dòng data đầu tiên bị parser lấy làm header.
- Chuẩn hóa số cột của bảng Markdown.
- Kế thừa header cho bảng nhiều trang.
- Với bảng nhiều trang, nếu trang sau chỉ còn dòng kiểu `9 Công nghệ tài chính`, tự đưa lại vào bảng với các cột còn lại để trống.
- Chuẩn hóa dòng chấm biểu mẫu thành placeholder dễ đọc hơn.
- Chuẩn hóa checkbox OCR dạng `O`, `0`, `□` thành `[ ]` khi đi cùng Có/Không/Nam/Nữ.

## 4. LlamaParse prompt

Cập nhật `llamaparse_engine.py`:

- Nhắc rõ LlamaParse không được biến văn bản thường thành bảng.
- Nhắc rõ nếu bảng kéo dài qua trang sau thì phải lặp lại header bảng.
- Nhắc rõ biểu mẫu/tờ khai phải giữ trường thông tin, checkbox, dòng chấm.

## 5. Router

Cập nhật `hybrid_page_router.py`:

- Log thêm `likely_form`, `raster_table`, `raster_form`, `h`, `v` để dễ debug.
- Output LlamaParse cũng được chạy qua lớp sửa lỗi chung/từ điển CTU.
- Output cuối được chạy qua `postprocess_final_markdown()` trước khi ghi file.
