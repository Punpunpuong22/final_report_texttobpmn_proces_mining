"""Cấu hình của pipeline: tham số mô phỏng, kịch bản và thiết lập riêng cho từng quy trình.

Mọi con số ở đây là GIẢ ĐỊNH để minh hoạ phương pháp. Khi có số liệu thật
(thời gian từng bước, số người mỗi làn, thời hạn theo văn bản), hãy thay vào.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Thời gian xử lý mặc định (phút) theo loại công việc BPMN, dùng khi tệp BPMN không khai báo.
# Hiệu chỉnh để quy trình nghỉ phép, kịch bản thuận lợi, cho khoảng 50 phút làm việc mỗi hồ sơ
# như text2BPMN hiển thị.
DEFAULT_MINUTES = {
    "task": 20, "userTask": 30, "manualTask": 30, "serviceTask": 5, "scriptTask": 2,
    "sendTask": 5, "receiveTask": 10, "businessRuleTask": 5, "subProcess": 30,
}
TASK_TAGS = frozenset(DEFAULT_MINUTES)
# Công việc do hệ thống làm: không xếp hàng, không chiếm năng lực của làn.
SYSTEM_TYPES = frozenset({"serviceTask", "scriptTask", "businessRuleTask"})
# Từ khoá nhận diện nhánh "thuận" của cổng loại trừ (XOR).
POSITIVE_WORDS = ("có", "đạt", "đồng ý", "trúng", "duyệt", "yes", "ok")
NEGATIVE_WORDS = ("không", "từ chối", "no", "hết")

# Bốn kịch bản. Hai kịch bản đầu ứng với hai nút "Việc suôn sẻ" và "Nhiều trục trặc" của text2BPMN.
#   p_positive: xác suất đi nhánh thuận ở mỗi cổng XOR
#   p_rework:   xác suất một bước phải làm lại (tối đa 4 lần)
#   mean_gap:   khoảng cách trung bình giữa hai hồ sơ đến (phút, phân phối mũ)
#   deviation:  tỷ lệ hồ sơ bị cài sai lệch (bỏ bước hoặc đảo thứ tự)
DEFAULT_SCENARIOS = {
    "S1_suon_se":   dict(p_positive=0.90, p_rework=0.05, mean_gap=40, deviation=0.0),
    "S2_truc_trac": dict(p_positive=0.30, p_rework=0.33, mean_gap=40, deviation=0.0),
    "S3_qua_tai":   dict(p_positive=0.90, p_rework=0.05, mean_gap=25, deviation=0.0),
    "S4_vi_pham":   dict(p_positive=0.90, p_rework=0.05, mean_gap=40, deviation=0.10),
}

# Thiết lập riêng cho từng quy trình, tra theo thuộc tính `name` của <bpmn:process>.
#   rules:        luật nghiệp vụ trích từ văn bản gốc
#                 ("truoc", A, B)      A phải xảy ra trước B
#                 ("khac_nguoi", A, B) A và B do hai người khác nhau thực hiện
#   automate:     bước đề xuất tự động hoá trong TO-BE (thay đổi C3)
#   repair_flows: các sequenceFlow cần xoá để sửa lỗi cấu trúc (thay đổi C0)
PROCESS_PRESETS = {
    "Quy trình nghỉ phép": dict(
        rules=[("truoc", "Xem xét đơn", "Ghi nhận nghỉ phép"),
               ("truoc", "Xem xét đơn", "Ghi lý do từ chối"),
               ("khac_nguoi", "Xem xét đơn", "Ghi nhận nghỉ phép")],
        automate="Ghi nhận nghỉ phép",
    ),
    "Quy trình tuyển dụng": dict(
        rules=[("truoc", "Phỏng vấn", "Gửi offer"),
               ("truoc", "Gửi offer", "Xác nhận offer"),
               ("khac_nguoi", "Sàng lọc hồ sơ", "Phỏng vấn")],
        automate="Gửi thư từ chối",
    ),
    "Quy_trinh_Dat_Hang": dict(
        rules=[("truoc", "Soạn hàng", "Xuất hóa đơn")],
        repair_flows=["P1_Flow_4", "P1_Flow_10", "P1_Flow_11"],
    ),
}


@dataclass
class Config:
    """Tham số của một lần chạy. Trường để None sẽ lấy theo PROCESS_PRESETS."""

    seed: int = 42
    n_cases: int = 200                       # giống ô "Thử với bao nhiêu hồ sơ" của text2BPMN
    start_time: datetime = datetime(2026, 3, 2, 8, 0)
    sla_minutes: float | None = None         # None = 1,5 × P90 thời gian lưu trú của kịch bản đầu
    task_minutes: dict = field(default_factory=dict)   # ghi đè theo tên bước, vd {"Xem xét đơn": 25}
    default_minutes: dict = field(default_factory=lambda: dict(DEFAULT_MINUTES))
    scenarios: dict = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_SCENARIOS.items()})
    capacity: dict | None = None             # số người mỗi làn; None = 1 người mỗi làn
    branch_p: dict = field(default_factory=dict)  # {(tên cổng, nhãn nhánh): xác suất}
    rework_p: dict = field(default_factory=dict)  # {tên bước: xác suất làm lại}
    rules: list | None = None
    automate: str | None = None              # "" để tắt C3
    repair_flows: list | None = None
    n_rep: int = 10                          # số lần lặp khi so sánh AS-IS và TO-BE
    whatif_scenarios: tuple = ("S1_suon_se", "S2_truc_trac", "S3_qua_tai")
    part1_log_dir: str | None = None         # thư mục chứa log CSV/XES do text2BPMN xuất (nếu có)

    def resolve(self, process_name: str) -> "Config":
        """Điền các trường None bằng thiết lập có sẵn của quy trình."""
        p = PROCESS_PRESETS.get(process_name, {})
        if self.rules is None:
            self.rules = list(p.get("rules", []))
        if self.automate is None:
            self.automate = p.get("automate", "")
        if self.repair_flows is None:
            self.repair_flows = list(p.get("repair_flows", []))
        return self
