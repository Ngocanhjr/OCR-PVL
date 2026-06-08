"""
loi_chung_van_ban.py
LỚP 1 - Xử lý lỗi OCR thường gặp trong văn bản hành chính, quy định, quyết định, biểu mẫu.

Nguyên tắc:
- Chỉ sửa lỗi có tính phổ quát, không phụ thuộc một file cụ thể.
- Không đoán nội dung pháp lý nếu thiếu bằng chứng.
- Các lỗi riêng từng file đưa sang `loi_rieng_it_gap.py` để cảnh báo hoặc tùy chọn sửa bằng file cấu hình.
"""

from __future__ import annotations

import re
from config import lam_sach_text, lam_sach_dong


DANH_SACH_BULLET = {
    "●": "•",
    "·": "•",
    "▪": "•",
    "": "•",
    "": "-",
    "–": "–",  # giữ nguyên gạch ngang dài
    "—": "–",
    "−": "-",
}


def chuan_hoa_ky_tu_co_ban(text: str) -> str:
    """Chuẩn hóa ký tự OCR thường gặp nhưng không làm mất nghĩa văn bản.

    Ví dụ: chuẩn hóa bullet, gạch ngang dài, khoảng trắng quanh dấu câu.
    Không đổi dấu `–` thành `-` vì văn bản hành chính hay dùng `–` trong tên chương trình.
    """

    if not text:
        return ""

    text = str(text)
    for src, dst in DANH_SACH_BULLET.items():
        text = text.replace(src, dst)

    # Dấu ngoặc kép OCR có thể ra nhiều mã Unicode khác nhau.
    text = text.replace("„", "“").replace("‟", "”")
    text = text.replace("''", '"').replace("``", '"')

    # Chuẩn hóa khoảng trắng quanh dấu câu.
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([([{“])\s+", r"\1", text)
    text = re.sub(r"\s+([)\]}”])", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    return lam_sach_text(text)


def sua_email_va_duong_link(text: str) -> str:
    """Sửa email/link bị OCR nhầm ký tự @ hoặc dính khoảng trắng.

    Đây là rule phổ quát, không biết trước email cụ thể.
    Ví dụ có thể sửa: `abc (Qctu.edu.vn`, `abc Qctu.edu.vn`, `abc 0ctu.edu.vn`.
    """

    if not text:
        return ""

    text = re.sub(
        r"([A-Za-z0-9._%+\-]+)\s*[\(\[]?\s*(?:@|Q|O|0|©|ⓐ)\s*([A-Za-z0-9.\-]+\.(?:vn|com|edu\.vn|org|net))",
        r"\1@\2",
        text,
        flags=re.IGNORECASE,
    )

    # Sửa khoảng trắng bị chèn vào URL.
    text = re.sub(r"(https?://)\s+", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"(www\.)\s+", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(/[^\s]*)", r"\1", text)
    return text


def sua_so_dien_thoai(text: str) -> str:
    """Chuẩn hóa số điện thoại bị tách quá nhiều khoảng trắng.

    Hàm chỉ gộp trong các cụm có dấu hiệu là điện thoại, không gộp toàn bộ số trong văn bản.
    """

    if not text:
        return ""

    def repl(match: re.Match) -> str:
        prefix = match.group(1)
        number = match.group(2)
        number = re.sub(r"\s+", "", number)
        return f"{prefix}{number}"

    return re.sub(r"\b(ĐT\s*:?\s*|Điện thoại\s*:?\s*)([0-9][0-9 .\-]{7,})", repl, text, flags=re.IGNORECASE)


def sua_loi_tieng_viet_pho_bien(text: str) -> str:
    """Sửa lỗi OCR phổ biến có tính tổng quát trong văn bản hành chính.

    Nhóm rule này chỉ chứa lỗi có xác suất đúng cao, lặp lại ở nhiều tài liệu: 
    tên cơ quan, thuật ngữ pháp lý, thuật ngữ biểu mẫu và lỗi dấu tiếng Việt thường gặp.
    Không sửa số hiệu/ngày tháng cụ thể nếu không có bằng chứng từ file gốc.
    """

    if not text:
        return ""

    rules = [
        # Từ khóa pháp lý/hành chính phổ biến.
        (r"\bCăn\s+cử\b", "Căn cứ"),
        (r"\bCăn\s+củ\b", "Căn cứ"),
        (r"\bCăn\s+cửu\b", "Căn cứ"),
        (r"\btin dụng\b", "tín dụng"),
        (r"\btin\s+dụng\b", "tín dụng"),
        (r"\bđảo tạo\b", "đào tạo"),
        (r"\bĐào tào\b", "Đào tạo"),
        (r"\bđề\s+giải ngân\s+v[ôo]n\s+vay\b", "để giải ngân vốn vay"),
        (r"\bđề\s+hỗ trợ\b", "để hỗ trợ"),
        (r"\bkỳ han\b", "kỳ hạn"),
        (r"\bkỳ hạrn\b", "kỳ hạn"),
        (r"\bv[ôo]n vay\b", "vốn vay"),
        (r"\btỉnh hình\b", "tình hình"),
        (r"\bthay döi\b", "thay đổi"),
        (r"\bnganh, linh vuc\b", "ngành, lĩnh vực"),
        (r"\bnghi học\b", "nghỉ học"),
        (r"\bđóng dầu\b", "đóng dấu"),
        (r"\bnghiện cứu sinh\b", "nghiên cứu sinh"),
        (r"\bnghi[êe]n cứu sinh\b", "nghiên cứu sinh"),
        (r"\bthạc sỹ\b", "thạc sĩ"),
        (r"\bhọc bồng\b", "học bổng"),
        (r"\bđỉnh kèm\b", "đính kèm"),
        (r"\bkhoá học\b", "khóa học"),

        # Tên quốc gia/cơ quan thường bị sai hoa-thường hoặc mất dấu trong OCR scan.
        (r"\bviệt nam\b", "Việt Nam"),
        (r"\bnhà nước việt nam\b", "Nhà nước Việt Nam"),
        (r"\bngân hàng nhà nước việt nam\b", "Ngân hàng Nhà nước Việt Nam"),
        (r"\bbộ tài chính\b", "Bộ Tài chính"),
        (r"\bbộ giáo dục và đào tạo\b", "Bộ Giáo dục và Đào tạo"),
        (r"\bngân hàng chính sách xã hội\b", "Ngân hàng Chính sách xã hội"),
        (r"\bngân hàng chính sách xả hội\b", "Ngân hàng Chính sách xã hội"),
        (r"\bThủ tướng chính phủ\b", "Thủ tướng Chính phủ"),
        (r"\bphó thủ tướng chính phủ\b", "Phó Thủ tướng Chính phủ"),
        (r"\bchính phủ\b", "Chính phủ"),
        (r"\bCộng hòa xã hội chủ nghĩa việt nam\b", "Cộng hòa xã hội chủ nghĩa Việt Nam"),
        (r"\bCọng hòa xã hội chủ nghĩa việt nam\b", "Cộng hòa xã hội chủ nghĩa Việt Nam"),
        (r"\bCÒ G HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\b", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"),

        # CTU/giáo dục.
        (r"\bDai hoc\b", "Đại học"),
        (r"\bDẠI HỌC\b", "ĐẠI HỌC"),
        (r"\bCan Tho\b", "Cần Thơ"),
        (r"\bCAN THO\b", "CẦN THƠ"),
        (r"\bQuyet dinh\b", "Quyết định"),
        (r"\bQUYET DINH\b", "QUYẾT ĐỊNH"),
        (r"\bThong bao\b", "Thông báo"),
        (r"\bTHONG BAO\b", "THÔNG BÁO"),
        (r"\bSinh vien\b", "Sinh viên"),
        (r"\bSINH VIEN\b", "SINH VIÊN"),
        (r"\bHoc vu\b", "Học vụ"),
        (r"\bHOC VU\b", "HỌC VỤ"),
        (r"\bCong tac sinh vien\b", "Công tác sinh viên"),
        (r"\bCONG TAC SINH VIEN\b", "CÔNG TÁC SINH VIÊN"),
        (r"\bPhong Dao tao\b", "Phòng Đào tạo"),
        (r"\bDao tao\b", "Đào tạo"),
        (r"\bHieu truong\b", "Hiệu trưởng"),
        (r"\bUu tiên\b", "Ưu tiên"),

        # Biểu mẫu/tờ khai.
        (r"\bM[ẪÃA]U\s+2\s+Ở\s+KÍ:?\s+AI\s+THÔNG\s+TIN\b", "MẪU TỜ KHAI THÔNG TIN"),
        (r"\bMAU\s+T[OỜ]\s+KHAI\b", "MẪU TỜ KHAI"),
        (r"\bNGÂN\s+JANG\s+CHÍNH\s+SÁCH\s+XÃ\s+HỘI\b", "NGÂN HÀNG CHÍNH SÁCH XÃ HỘI"),
        (r"\bTỜ\s+KHAI\s+THÔNG\s+TIN\s+HẰNG\s+NÃM\b", "TỜ KHAI THÔNG TIN HẰNG NĂM"),
        (r"\bMÀ\s+50\s*-U.*?THÔNG\s+TIN\s+HÀNG\s+NĂM\s+CỦA\s+NGƯỜI\s+HỌC\b", "MẪU TỜ KHAI THÔNG TIN HẰNG NĂM CỦA NGƯỜI HỌC"),
        (r"\bCCCD\s+số\b", "CCCD số"),
        (r"\bCCD\s+số\b", "CCCD số"),
        (r"\bngày cấp\b", "ngày cấp"),
    ]

    for pattern, replacement in rules:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def nghi_ngo_co_ky_tu_dac_biet(line: str) -> bool:
    """Kiểm tra một dòng có nguy cơ VietOCR nhận sai ký tự đặc biệt hay không.

    Dùng để quyết định có fallback PaddleOCR recognition cho crop đó không.
    """

    line = lam_sach_dong(line)
    if not line:
        return False

    patterns = [
        r"\?",              # Dấu ? thường là @, –, “”, ký tự lạ bị OCR sai.
        r"Email",
        r"ĐT|Điện thoại",
        r"www|http",
        r"\(Q|\sQ[A-Za-z0-9]",  # @ bị thành Q hoặc (Q.
        r"[A-Za-z0-9._%+\-]+\s+[QO0]\s*[A-Za-z0-9.\-]+\.(vn|com|edu\.vn)",
    ]
    return any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in patterns)


def sua_ky_tu_dac_biet_chung(text: str) -> str:
    """Sửa dấu đặc biệt theo quy luật chung, không theo tên riêng của file.

    Ví dụ: `truyền thông? Đại học` thường là thiếu dấu gạch ngang dài giữa 2 cụm danh từ.
    Rule này chỉ áp dụng khi trước/sau `?` là cụm chữ có dạng tên đơn vị hoặc tên chương trình.
    """

    if not text:
        return ""

    # Nếu ? nằm giữa hai cụm chữ viết hoa/viết thường có khoảng trắng, khả năng cao là dấu –.
    text = re.sub(
        r"([A-Za-zÀ-ỹ0-9\)]+(?:\s+[A-Za-zÀ-ỹ0-9\)]+){0,4})\?\s+([A-ZĐÀ-Ỹ][A-Za-zÀ-ỹ0-9]+)",
        r"\1 – \2",
        text,
    )

    # Nếu ? bao quanh một cụm in hoa ngắn, có thể là dấu ngoặc kép bị mất.
    # Không tự sửa mạnh toàn cục; chỉ làm sạch trường hợp nhiều ? dính sát gây khó đọc.
    text = text.replace(" ? ", " – ")
    return text




def sua_khoang_trang_dinh_chu(text: str) -> str:
    """Sửa lỗi mất khoảng trắng do PDF text layer/OCR dính chữ.

    Hàm chỉ sửa các mẫu có độ an toàn cao trong văn bản hành chính CTU:
    - `số16/2016` -> `số 16/2016`
    - `phiếu“Bảng...` -> `phiếu “Bảng...`
    - `CTSVtập hợp`, `ĐRLcấp Trường`, `Khoatổng hợp` -> thêm khoảng trắng.

    Không dùng rule quá rộng kiểu tách mọi chữ thường + chữ hoa vì có thể phá tên riêng
    hoặc mã số văn bản.
    """
    if not text:
        return ""

    # Thêm khoảng trắng sau các từ khóa hành chính trước số/mã văn bản.
    text = re.sub(r"\b(số|Số)(\d)", r"\1 \2", text)
    text = re.sub(r"\b(ngày)(\d{1,2})\b", r"\1 \2", text, flags=re.IGNORECASE)

    # Thêm khoảng trắng trước/sau ngoặc kép tiếng Việt khi bị dính vào chữ.
    text = re.sub(r"([A-Za-zÀ-ỹ0-9])([“\"])", r"\1 \2", text)
    text = re.sub(r"([”\"])([A-Za-zÀ-ỹ0-9])", r"\1 \2", text)

    # Các cụm viết tắt thường bị PyMuPDF/OCR dính vào chữ kế tiếp.
    abbreviations = ["CTSV", "ĐRL", "CVHT", "QĐ", "BGH", "SV", "CTCT", "KHTH", "SQDB", "TTGDQP", "QK9"]
    for abbr in abbreviations:
        text = re.sub(rf"\b({abbr})(?=[A-Za-zÀ-ỹ])", rf"\1 ", text)

    # Một số mẫu dính chữ phổ biến trong tài liệu CTU.
    safe_rules = [
        (r"\b(Khoa)(tổng|thông|xét|cấp)\b", r"\1 \2"),
        (r"\b(Phòng)(CTSV|CTCT|Đào tạo|KHTH)\b", r"\1 \2"),
        (r"\b(PhòngCTSV)\b", "Phòng CTSV"),
        (r"\b(đơn vị)(quản lý|đào tạo)\b", r"\1 \2"),
        (r"\b(sinh viên)(đang|nhận|dự|có)\b", r"\1 \2"),
    ]
    for pattern, repl in safe_rules:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    return lam_sach_text(text)

def hau_xu_ly_loi_chung(text: str) -> str:
    """Chạy toàn bộ lớp 1: lỗi OCR phổ biến trong văn bản hành chính."""

    text = chuan_hoa_ky_tu_co_ban(text)
    text = sua_email_va_duong_link(text)
    text = sua_so_dien_thoai(text)
    text = sua_loi_tieng_viet_pho_bien(text)
    text = sua_khoang_trang_dinh_chu(text)
    text = sua_ky_tu_dac_biet_chung(text)
    text = chuan_hoa_ky_tu_co_ban(text)
    # Bỏ watermark scanner phổ biến nếu OCR nhận vào nội dung.
    text = re.sub(r"(?im)^\s*Scanned\s+with\s+(cs\s*)?CamScanner\s*$", "", text)
    text = re.sub(r"(?im)^\s*CamScanner\s*$", "", text)
    return lam_sach_text(text)
