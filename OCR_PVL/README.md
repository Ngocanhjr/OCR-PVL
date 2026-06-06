# OCR PadViet + LlamaParse TableSafe

Bản đã gộp còn **một file chạy chính duy nhất: `main.py`**.

Mục tiêu của bản này:

- Không còn `main_hybrid_llama.py`, `main_table_safe.py` hoặc `main_LlamaParse.py`.
- Không dùng PyMuPDF để tạo bảng, tránh lỗi biến đoạn văn thường thành bảng giả.
- Trang văn bản thường dùng local: PyMuPDF text-only hoặc PaddleOCR + VietOCR.
- Trang có bảng/lưu đồ thật dùng LlamaParse để xuất Markdown table/layout.
- Có thể ép trang bảng bằng `--table-pages` để tránh detector bỏ sót.

## Cài thư viện bổ sung

```powershell
python -m pip install -r requirements.txt
```

Nếu dùng LlamaParse, cần cấu hình API key:

```powershell
$env:LLAMA_CLOUD_API_KEY="API_KEY_CUA_BAN"
setx LLAMA_CLOUD_API_KEY "API_KEY_CUA_BAN"
```

Sau `setx`, đóng terminal VS Code rồi mở lại nếu muốn key có hiệu lực vĩnh viễn.

## Lệnh chạy khuyến nghị

Chạy PDF theo kiểu TableSafe tự động:

```powershell
python main.py "D:\Code\CTU_Student_Service\Dataset_Attachments\PDFs\CTSV\QuyTrinh4-Congtacsinhvien.pdf" --engine auto-page --page-start 1 --page-end 4
```

Với file `QuyTrinh4-Congtacsinhvien.pdf`, trang 4 là bảng/lưu đồ thật, nên có thể ép trang 4 qua LlamaParse:

```powershell
python main.py "D:\Code\CTU_Student_Service\Dataset_Attachments\PDFs\CTSV\QuyTrinh4-Congtacsinhvien.pdf" --engine auto-page --page-start 1 --page-end 4 --table-pages 4 --llama-tier agentic
```

Nếu bảng khó hoặc nhiều ô bị gộp:

```powershell
python main.py "D:\Code\CTU_Student_Service\Dataset_Attachments\PDFs\CTSV\QuyTrinh4-Congtacsinhvien.pdf" --engine auto-page --page-start 1 --page-end 4 --table-pages 4 --llama-tier agentic_plus --spatial
```

Chạy hoàn toàn local, không cần API key, không tạo bảng:

```powershell
python main.py "file.pdf" --engine local --page-start 1 --page-end 4
```

Dùng LlamaParse cho toàn bộ file/trang:

```powershell
python main.py "file.pdf" --engine llamaparse --llama-tier agentic --page-start 1 --page-end 2
```

## Ý nghĩa engine

| Engine | Cách xử lý | Khi dùng |
|---|---|---|
| `auto-page` | Trang text dùng local, trang bảng/lưu đồ dùng LlamaParse | Khuyến nghị cho tài liệu CTU |
| `local` | Chỉ dùng local, không LlamaParse, không bảng PyMuPDF | Khi không có API key hoặc chỉ cần text |
| `llamaparse` | Toàn bộ file/trang dùng LlamaParse | PDF scan khó, bảng/form rất phức tạp |

## Cấu trúc file chính

| File | Vai trò |
|---|---|
| `main.py` | File chạy chính duy nhất |
| `hybrid_page_router.py` | Router theo từng trang PDF |
| `document_page_analyzer.py` | Nhận diện trang có bảng/lưu đồ thật, không trích bảng |
| `llamaparse_engine.py` | Gọi LlamaParse |
| `ocr_engine.py` | PaddleOCR + VietOCR local |
| `markdown_layout.py` | Gộp dòng và định dạng Markdown |
| `page_markers.py` | Chuẩn hóa page marker RAG: dùng `<!-- page: n -->`, không dùng heading `## Trang n` |
| `common_fix.py`, `ctu_terms.py`, `rare_fix.py` | Hậu xử lý lỗi OCR/văn bản CTU |


## Chuẩn page marker cho RAG

Output mới chỉ dùng page marker dạng comment HTML:

```md
<!-- page: 11 -->
```

Không còn xuất `## Trang 11` làm heading. Lý do: nếu chunker tách theo heading Markdown, `## Trang 11` sẽ bị hiểu nhầm là section nghiệp vụ và làm nhiễu chunk/retrieval.

Code vẫn đọc được output cũ có `## Trang n`; lớp hậu xử lý sẽ tự đổi về marker comment trước khi ghi file cuối.

## Lưu ý quan trọng

- Không chạy các file main cũ nữa vì đã bị xóa khỏi bản này.
- Muốn trang 4 tạo bảng chắc chắn thì thêm `--table-pages 4`.
- `--aggressive-tables` chỉ dùng khi chắc chắn trang đó là bảng/lưu đồ thật, không bật mặc định.

## Cập nhật sửa lỗi tên bảng bị lặp trong header

Bản này đã thêm hậu xử lý trong `llamaparse_engine.py`:

- Nếu LlamaParse trả về bảng dạng `TÊN BẢNG<br/>Bước`, `TÊN BẢNG<br/>Lưu đồ`, ...
- Code sẽ đưa `TÊN BẢNG` ra thành heading riêng phía trên bảng.
- Header bảng chỉ còn tên cột thật: `Bước`, `Lưu đồ`, `Nội dung công việc`, `Người thực hiện`, `Thời gian thực hiện`, `Ghi chú`.

Lý do: Markdown table chuẩn không hỗ trợ gộp cột (`colspan`), nên biểu diễn tên bảng tốt nhất là heading riêng phía trên bảng.

## Cấu hình API key bằng file `.env`

Tạo file `.env` cùng thư mục với `main.py`:

```env
LLAMA_CLOUD_API_KEY=llx_API_KEY_CUA_BAN
```

Cài thư viện đọc `.env` nếu chưa có:

```powershell
python -m pip install python-dotenv
```

Kiểm tra code có đọc được key không:

```powershell
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('OK' if os.getenv('LLAMA_CLOUD_API_KEY') else 'MISSING')"
```

File `.env` đã được đưa vào `.gitignore`, không được push lên Git. Chỉ push `.env.example` để làm mẫu.
