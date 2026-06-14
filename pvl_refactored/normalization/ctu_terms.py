"""
tu_dien_ctu.py
LỚP 2 - Từ điển / thuật ngữ thường gặp theo đề tài CTU Student Service.

Mục tiêu:
- Bảo vệ các thuật ngữ CTU, tên phòng ban, tên trường/khoa, loại thủ tục.
- Sửa các biến thể OCR phổ biến theo ngữ cảnh CTU.
- Không chứa lỗi riêng của một file cụ thể.
"""

from __future__ import annotations

import re
from config import chuan_hoa_de_so_khop, iter_dong_sach, lam_sach_text


# Thuật ngữ nên được giữ ổn định khi OCR tài liệu CTU.
THUAT_NGU_CTU = [
    "Đại học Cần Thơ",
    "Trường Đại học Cần Thơ",
    "Trường Công nghệ thông tin và truyền thông",
    "Phòng Đào tạo",
    "Phòng Công tác Sinh viên",
    "Công tác sinh viên",
    "Học vụ",
    "Học phần",
    "Sinh viên",
    "Điểm rèn luyện",
    "Miễn giảm học phí",
    "Tạm hoãn nghĩa vụ quân sự",
    "Vay vốn sinh viên",
    "Ngân hàng Chính sách xã hội",
    "Bộ Giáo dục và Đào tạo",
    "Bộ Tài chính",
    "Tờ khai thông tin",
    "Phụ lục",
    "Mẫu báo cáo",
    "Học sinh, sinh viên",
    "Học viên thạc sĩ",
    "Nghiên cứu sinh",
    "Giấy xác nhận sinh viên",
    "Đơn xin vắng thi",
    "Mở lớp học phần",
    "Biểu mẫu",
    "Quy định",
    "Quyết định",
    "Thông báo",
    "Công văn",
]

# Những sửa lỗi phổ biến theo ngữ cảnh CTU, an toàn hơn hardcode theo từng file.
MAU_SUA_CTU = [
    (r"\bDai hoc Can Tho\b", "Đại học Cần Thơ"),
    (r"\bDẠI HỌC CẦN THO\b", "ĐẠI HỌC CẦN THƠ"),
    (r"\bDai Hoc Can Tho\b", "Đại học Cần Thơ"),
    (r"\bTruong Dai hoc Can Tho\b", "Trường Đại học Cần Thơ"),
    (r"\bTruong Cong nghe thong tin va truyen thong\b", "Trường Công nghệ thông tin và truyền thông"),
    (r"\bCong nghe thong tin va truyen thong\b", "Công nghệ thông tin và truyền thông"),
    (r"\bPhong Cong tac Sinh vien\b", "Phòng Công tác Sinh viên"),
    (r"\bPhong Dao tao\b", "Phòng Đào tạo"),
    (r"\bDiem ren luyen\b", "Điểm rèn luyện"),
    (r"\bGiay xac nhan sinh vien\b", "Giấy xác nhận sinh viên"),
    (r"\bVay von sinh vien\b", "Vay vốn sinh viên"),
    (r"\bTam hoan nghia vu quan su\b", "Tạm hoãn nghĩa vụ quân sự"),
    (r"\bNgan hang Chinh sach xa hoi\b", "Ngân hàng Chính sách xã hội"),
    (r"\bBo Giao duc va Dao tao\b", "Bộ Giáo dục và Đào tạo"),
    (r"\bBo Tai chinh\b", "Bộ Tài chính"),
    (r"\bHoc sinh, sinh vien\b", "Học sinh, sinh viên"),
    (r"\bHoc vien thac si\b", "Học viên thạc sĩ"),
    (r"\bNghien cuu sinh\b", "Nghiên cứu sinh"),
    (r"\bTo khai thong tin\b", "Tờ khai thông tin"),
]


def ap_dung_mau_sua_ctu(text: str) -> str:
    """Áp dụng các mẫu sửa thuật ngữ CTU có độ an toàn cao."""

    if not text:
        return ""
    for pattern, replacement in MAU_SUA_CTU:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def tim_thuat_ngu_ctu_gan_dung(line: str) -> list[str]:
    """Tìm thuật ngữ CTU có thể liên quan đến một dòng OCR.

    Hàm này không tự sửa, chỉ giúp lớp báo cáo review biết dòng nào nên kiểm tra.
    """

    line_key = chuan_hoa_de_so_khop(line)
    if not line_key:
        return []

    found: list[str] = []
    for term in THUAT_NGU_CTU:
        term_key = chuan_hoa_de_so_khop(term)
        if term_key and term_key in line_key:
            found.append(term)
    return found


def bao_ve_thuat_ngu_viet_tat(text: str) -> str:
    """Chuẩn hóa một số viết tắt thường gặp trong tài liệu CTU.

    Chỉ sửa khi pattern rất rõ ràng để tránh làm sai nội dung.
    """

    if not text:
        return ""

    viet_tat = {
        r"\bCTSV\b": "CTSV",
        r"\bP\.\s*CTSV\b": "P. CTSV",
        r"\bP\.\s*ĐT\b": "P. ĐT",
        r"\bCTU\b": "CTU",
        r"\bDHCT\b": "ĐHCT",
        r"\bĐHCT\b": "ĐHCT",
    }
    for pattern, replacement in viet_tat.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def canh_bao_thuat_ngu_ctu(text: str) -> list[str]:
    """Tạo cảnh báo cho những dòng có vẻ là thuật ngữ CTU nhưng OCR còn dấu hiệu lỗi."""
    warnings: list[str] = []
    for idx, line in iter_dong_sach(text):
        related = tim_thuat_ngu_ctu_gan_dung(line)
        if related and ("?" in line or re.search(r"\b[Dd]ai hoc|[Cc]an [Tt]ho|[Ss]inh vien\b", line)):
            warnings.append(f"Dòng {idx}: nên kiểm tra thuật ngữ CTU gần {related[:3]} -> {line}")
    return warnings


def hau_xu_ly_tu_dien_ctu(text: str) -> str:
    """Chạy lớp 2: sửa thuật ngữ CTU và bảo vệ viết tắt phổ biến."""

    text = ap_dung_mau_sua_ctu(text)
    text = bao_ve_thuat_ngu_viet_tat(text)
    return lam_sach_text(text)
