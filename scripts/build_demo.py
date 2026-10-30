"""Tạo bản trình diễn tĩnh docs/demo.html của giao diện web.

Chạy pipeline trên ba tệp BPMN mẫu, đóng gói kết quả từng bước (bảng, hình PNG dạng data URI) vào chính
trang static/index.html qua biến window.DEMO. Trang tạo ra mở được bằng trình duyệt, không cần máy chủ.

    PYTHONHASHSEED=2 PYTHONPATH=src python scripts/build_demo.py [--n-rep 10] [--out docs/demo.html]
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from text2bpmn_mining import Config, Pipeline  # noqa: E402
from text2bpmn_mining.report import STEPS, serialize_step  # noqa: E402

LABELS = {"quy-trinh-nghi-phep": "Nghỉ phép", "quy-trinh-tuyen-dung": "Tuyển dụng", "quy-trinh-dat-hang": "Đặt hàng"}


def run_one(path: str, n_rep: int, work: str) -> dict:
    stem = os.path.splitext(os.path.basename(path))[0]
    p = Pipeline(path, os.path.join(work, stem), Config(n_rep=n_rep, part1_log_dir=os.path.join(work, "_no_logs")))
    steps = []
    for i, (key, _, _) in enumerate(STEPS, 1):
        getattr(p, key)()
        plt.close("all")
        steps.append(serialize_step(p, i))
        print(f"  {stem}: bước {i} xong", flush=True)
    images = {}
    for s in steps:
        for im in s["images"]:
            fp = os.path.join(p.out, im["file"])
            if os.path.exists(fp):
                images[im["file"]] = "data:image/png;base64," + base64.b64encode(open(fp, "rb").read()).decode()
    return dict(label=LABELS.get(stem, stem), process=p.M["name"], bpmn=os.path.basename(path), steps=steps, images=images)


def main():
    if os.environ.get("PYTHONHASHSEED") != "2":
        print("Lưu ý: đặt PYTHONHASHSEED=2 để chỉ số Heuristics Miner trùng với báo cáo.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-rep", type=int, default=10)
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "demo.html"))
    a = ap.parse_args()
    order = ["quy-trinh-nghi-phep", "quy-trinh-tuyen-dung", "quy-trinh-dat-hang"]
    files = sorted(glob.glob(os.path.join(ROOT, "data", "bpmn", "*.bpmn")),
                   key=lambda f: order.index(os.path.basename(f)[:-5]) if os.path.basename(f)[:-5] in order else 9)
    with tempfile.TemporaryDirectory() as work:
        procs = [run_one(f, a.n_rep, work) for f in files]
    page = open(os.path.join(ROOT, "src", "text2bpmn_mining", "web", "static", "index.html"), encoding="utf-8").read()
    data = json.dumps(dict(processes=procs), ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("<script>", f"<script>window.DEMO = {data};</script>\n<script>", 1)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(page)
    print(f"Đã ghi {a.out} ({os.path.getsize(a.out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
