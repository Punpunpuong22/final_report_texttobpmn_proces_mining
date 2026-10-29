"""Chạy pipeline từ dòng lệnh.

    python -m text2bpmn_mining data/bpmn/quy-trinh-nghi-phep.bpmn
    python -m text2bpmn_mining data/bpmn/*.bpmn --n-rep 10 --out outputs
"""
from __future__ import annotations

import argparse
import os
import sys

from .config import Config
from .pipeline import Pipeline


def main(argv=None):
    # Một vài chỉ số của Heuristics Miner trong pm4py phụ thuộc thứ tự duyệt tập hợp của Python.
    # Cố định PYTHONHASHSEED để mọi lần chạy từ dòng lệnh cho cùng kết quả.
    if os.environ.get("PYTHONHASHSEED") is None and argv is None:
        os.environ["PYTHONHASHSEED"] = "2"   # giá trị dùng cho kết quả trong báo cáo
        os.execv(sys.executable, [sys.executable, "-m", "text2bpmn_mining", *sys.argv[1:]])
    ap = argparse.ArgumentParser(prog="text2bpmn_mining", description="Khai phá quy trình trên BPMN của text2BPMN")
    ap.add_argument("bpmn", nargs="+", help="một hoặc nhiều tệp .bpmn")
    ap.add_argument("--out", default="outputs", help="thư mục gốc chứa kết quả (mặc định: outputs)")
    ap.add_argument("--n-cases", type=int, default=200, help="số hồ sơ mỗi kịch bản")
    ap.add_argument("--n-rep", type=int, default=10, help="số lần lặp khi so sánh AS-IS và TO-BE")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sla", type=float, default=None, help="thời hạn xử lý (phút); bỏ trống = 1,5 × P90 của S1")
    ap.add_argument("--logs", default=None, help="thư mục log CSV/XES của text2BPMN (mặc định data/part1_logs/<tên tệp>)")
    a = ap.parse_args(argv)
    for path in a.bpmn:
        stem = os.path.splitext(os.path.basename(path))[0]
        cfg = Config(seed=a.seed, n_cases=a.n_cases, n_rep=a.n_rep, sla_minutes=a.sla, part1_log_dir=a.logs)
        Pipeline(path, os.path.join(a.out, stem), cfg).run()


if __name__ == "__main__":
    main()
