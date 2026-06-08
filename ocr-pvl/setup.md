# Hướng dẫn chạy OCR_PVL

File chạy chính của project là `main.py`.

Có 2 trường hợp thường gặp:

- Windows local, chạy bằng CMD trong VS Code.
- GitHub Codespaces/Linux, chạy bằng terminal bash.

## 1. Windows local - CMD trong VS Code

Mở terminal CMD trong VS Code:

```cmd
Terminal > New Terminal > mũi tên cạnh dấu + > Command Prompt
```

Đi vào thư mục project:

```cmd
cd /d "E:\RHNA\Visual\NLCS\CTU-Service\ocr\OCR_PVL"
```

Tạo môi trường ảo nếu chưa có:

```cmd
python -m venv .venv
```

Kích hoạt môi trường ảo:

```cmd
.venv\Scripts\activate.bat
```

Nếu kích hoạt thành công, prompt sẽ có dạng:

```cmd
(.venv) E:\RHNA\Visual\NLCS\CTU-Service\ocr\OCR_PVL>
```

Cài thư viện:

```cmd
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Kiểm tra chương trình:

```cmd
python main.py --help
```

### Chạy PDF local, không cần API key

```cmd
python main.py "D:\duong-dan\file.pdf" --engine local
```

Chỉ chạy một khoảng trang:

```cmd
python main.py "D:\duong-dan\file.pdf" --engine local --page-start 1 --page-end 4
```

### Chạy DOCX bằng LlamaParse

DOCX chỉ chạy được với `--engine llamaparse`.

Set API key tạm thời cho terminal hiện tại:

```cmd
set LLAMA_CLOUD_API_KEY=llx_API_KEY_CUA_BAN
```

Chạy DOCX:

```cmd
python main.py "D:\duong-dan\file.docx" --engine llamaparse
```

Chỉ định file output Markdown:

```cmd
python main.py "D:\duong-dan\file.docx" --engine llamaparse -o "output\file_docx.md"
```

Set API key vĩnh viễn trên Windows:

```cmd
setx LLAMA_CLOUD_API_KEY "llx_API_KEY_CUA_BAN"
```

Sau khi dùng `setx`, đóng terminal VS Code và mở lại để biến môi trường mới có hiệu lực.

## 2. Codespaces/Linux - terminal bash

Trong Codespaces, `.venv` thường có thư mục `bin`, không có `Scripts`.

Nếu đang ở thư mục gốc có `.venv` và thư mục `OCR_PVL`, kích hoạt môi trường ảo:

```bash
source .venv/bin/activate
```

Sau đó vào thư mục source:

```bash
cd OCR_PVL
```

Nếu chưa có `.venv`, tạo mới:

```bash
python -m venv .venv
source .venv/bin/activate
```

Nếu `.venv` nằm trong cùng thư mục với `main.py`, chạy:

```bash
source .venv/bin/activate
```

Cài thư viện:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Kiểm tra chương trình:

```bash
python main.py --help
```

### Chạy PDF local, không cần API key

```bash
python main.py "/duong-dan/file.pdf" --engine local
```

Chỉ chạy một khoảng trang:

```bash
python main.py "/duong-dan/file.pdf" --engine local --page-start 1 --page-end 4
```

### Chạy DOCX bằng LlamaParse

DOCX chỉ chạy được với `--engine llamaparse`.

Set API key tạm thời cho terminal hiện tại:

```bash
export LLAMA_CLOUD_API_KEY="llx_API_KEY_CUA_BAN"
```

Chạy DOCX:

```bash
python main.py "/duong-dan/file.docx" --engine llamaparse
```

Nếu file DOCX nằm cùng thư mục với `main.py`:

```bash
python main.py "file.docx" --engine llamaparse
```

Chỉ định file output Markdown:

```bash
python main.py "file.docx" --engine llamaparse -o "output/file_docx.md"
```

## 3. Chạy file scan/ảnh bằng local OCR

Nếu PDF scan hoặc file ảnh cần OCR local, có thể cần cài thêm các thư viện nặng:

```bash
python -m pip install paddleocr==2.9.1 paddlepaddle vietocr torch torchvision pillow
```

Trên Windows CMD cũng dùng lệnh Python tương tự:

```cmd
python -m pip install paddleocr==2.9.1 paddlepaddle vietocr torch torchvision pillow
```

Sau đó chạy:

```bash
python main.py "/duong-dan/file.pdf" --engine local --force-ocr
```

Hoặc trên Windows CMD:

```cmd
python main.py "D:\duong-dan\file.pdf" --engine local --force-ocr
```

## 4. Output

Nếu không truyền `-o`, output mặc định nằm trong thư mục:

```text
output
```

Mỗi file đầu ra sẽ có dạng:

```text
ten_file_structured.md
```

Báo cáo review nếu có sẽ nằm trong:

```text
output/review_reports
```

Ảnh render/cache nếu có sẽ nằm trong:

```text
output/temp_images
```

## 5. Lỗi thường gặp

### Lỗi: The system cannot find the path specified

Thường do gõ dính 2 lệnh CMD vào 1 dòng.

Sai:

```cmd
cd /d "E:\RHNA\Visual\NLCS\CTU-Service\ocr\OCR_PVL" .venv\Scripts\activate.bat
```

Đúng:

```cmd
cd /d "E:\RHNA\Visual\NLCS\CTU-Service\ocr\OCR_PVL"
.venv\Scripts\activate.bat
```

### Lỗi: không có .venv\Scripts

Nếu đang ở Codespaces/Linux thì dùng:

```bash
source .venv/bin/activate
```

Không dùng lệnh Windows:

```cmd
.venv\Scripts\activate.bat
```

### Lỗi: No module named dotenv

Chưa cài requirements. Chạy:

```bash
python -m pip install -r requirements.txt
```

Trên Windows CMD:

```cmd
python -m pip install -r requirements.txt
```

### Lỗi: No module named fitz

Chưa cài `PyMuPDF`. Chạy:

```bash
python -m pip install -r requirements.txt
```

Trên Windows CMD:

```cmd
python -m pip install -r requirements.txt
```

### Lỗi: thiếu LLAMA_CLOUD_API_KEY

Khi chạy DOCX hoặc `--engine llamaparse`, cần set API key.

Windows CMD:

```cmd
set LLAMA_CLOUD_API_KEY=llx_API_KEY_CUA_BAN
```

Codespaces/Linux:

```bash
export LLAMA_CLOUD_API_KEY="llx_API_KEY_CUA_BAN"
```

