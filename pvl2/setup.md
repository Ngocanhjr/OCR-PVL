# Hướng dẫn chạy OCR_PVL

File chạy chính của project là `main.py`.

Có 2 trường hợp thường gặp:

- Windows local, chạy bằng CMD trong VS Code.
- GitHub Codespaces/Linux, chạy bằng terminal bash.

## 0. Phiên bản yêu cầu

Nhánh này dùng code PaddleOCR API 2.x, vì vậy phải giữ đúng stack thư viện 2.x:

```text
Python: CPython 3.10, 3.11 hoặc 3.12, 64-bit
PaddleOCR: 2.9.1
PaddlePaddle: 2.6.2
VietOCR: 0.3.12
Torch: 2.4.1
TorchVision: 0.19.1
NumPy: >=1.24,<2.0
Pillow: >=10,<11
```

Khuyến nghị trên Windows local: dùng CPython 3.12 64-bit từ `python.org` hoặc Microsoft Store. Không dùng Python MSYS/MinGW như:

```text
C:\msys64\mingw64\bin\python.exe
C:\msys64\ucrt64\bin\python.exe
```

Các bản MSYS thường không có wheel phù hợp cho `paddlepaddle`, `torch`, `torchvision`.

Kiểm tra Python trước khi tạo venv:

```cmd
python --version
python -c "import sys, platform; print(sys.executable); print(platform.architecture()[0]); print(platform.machine())"
```

Kết quả cần là `64bit` và `AMD64`/`x86_64`.

## 1. Windows local - CMD trong VS Code

Mở terminal CMD trong VS Code:

```cmd
Terminal > New Terminal > mũi tên cạnh dấu + > Command Prompt
```

Đi vào thư mục project:

```cmd
cd /d "E:\RHNA\Visual\NLCS\CTU-Service\ocr\ocr-pvl"
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
(.venv) E:\RHNA\Visual\NLCS\CTU-Service\ocr\ocr-pvl>
```

Cài thư viện theo version đã pin:

```cmd
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Nếu môi trường đã từng cài PaddleOCR/PaddlePaddle 3.x, cài sạch lại:

```cmd
python -m pip uninstall -y paddleocr paddlepaddle paddlex
python -m pip install --force-reinstall -r requirements.txt
```

Kiểm tra version sau khi cài:

```cmd
python -c "import paddle, paddleocr, torch; print('paddle', paddle.__version__); print('paddleocr', paddleocr.__version__); print('torch', torch.__version__)"
```

Kết quả đúng:

```text
paddle 2.6.2
paddleocr 2.9.1
torch 2.4.1
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

Nếu đang ở thư mục gốc có `.venv` và thư mục `ocr-pvl`, kích hoạt môi trường ảo:

```bash
source .venv/bin/activate
```

Sau đó vào thư mục source:

```bash
cd ocr/ocr-pvl
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

Nếu PDF scan hoặc file ảnh cần OCR local, dùng đúng `requirements.txt`.
Không cài lẻ kiểu `pip install paddleocr paddlepaddle` vì pip sẽ kéo bản mới nhất 3.x.

```bash
python -m pip install -r requirements.txt
```

Trên Windows CMD cũng dùng lệnh Python tương tự:

```cmd
python -m pip install -r requirements.txt
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
cd /d "E:\RHNA\Visual\NLCS\CTU-Service\ocr\ocr-pvl" .venv\Scripts\activate.bat
```

Đúng:

```cmd
cd /d "E:\RHNA\Visual\NLCS\CTU-Service\ocr\ocr-pvl"
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

Thường do chưa cài `PyMuPDF` hoặc đang chạy nhầm Python ngoài `.venv`.
Kiểm tra:

```cmd
where python
python -c "import sys; print(sys.executable)"
```

Nếu đường dẫn không nằm trong `.venv\Scripts\python.exe`, kích hoạt lại venv.
Sau đó chạy:

```bash
python -m pip install -r requirements.txt
```

Trên Windows CMD:

```cmd
python -m pip install -r requirements.txt
```

### Lỗi: kéo nhầm PaddleOCR/PaddlePaddle 3.x

Code nhánh này dùng API PaddleOCR 2.x. Nếu thấy các lỗi như:

```text
Unknown argument: use_angle_cls
Unknown argument: use_gpu
OneDnnContext does not have the input Filter
ConvertPirAttribute2RuntimeAttribute
```

hãy kiểm tra version:

```cmd
python -c "import paddle, paddleocr; print(paddle.__version__); print(paddleocr.__version__)"
```

Version đúng là:

```text
paddle 2.6.2
paddleocr 2.9.1
```

Cài sạch lại:

```cmd
python -m pip uninstall -y paddleocr paddlepaddle paddlex
python -m pip install --force-reinstall -r requirements.txt
```

### Lỗi: pip báo không có paddlepaddle hoặc torch

Gần như chắc chắn đang dùng Python không phải CPython Windows 64-bit, thường là MSYS/MinGW.
Kiểm tra:

```cmd
where python
python -c "import sys, platform; print(sys.executable); print(platform.architecture()[0]); print(platform.machine())"
```

Không dùng:

```text
C:\msys64\mingw64\bin\python.exe
C:\msys64\ucrt64\bin\python.exe
```

Hãy tạo lại `.venv` bằng CPython 3.10/3.11/3.12 64-bit.

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

# Summary

```bash
cd /d E:\RHNA\Visual\NLCS\CTU-Service\ocr\ocr-pvl

python -m venv .venv

.venv\Scripts\activate.bat

where python

python -m pip install --upgrade pip

python -m pip install -r requirements.txt

python -c "import paddle, paddleocr, torch; print(paddle.__version__, paddleocr.__version__, torch.__version__)"

```
