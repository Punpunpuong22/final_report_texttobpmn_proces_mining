"""Giao diện web cho pipeline Phần 2.

Chạy:  python -m text2bpmn_mining.web          (mở http://127.0.0.1:8050)
Trên Colab: xem ô "Giao diện web" trong notebook.

Người dùng tải lên một tệp BPMN (hoặc chọn tệp mẫu) và, nếu có, các tệp log CSV/XES của text2BPMN;
máy chủ chạy tám bước của Pipeline trong một luồng nền, trả kết quả từng bước dưới dạng JSON.
"""
from __future__ import annotations

import glob
import io
import os
import shutil
import tempfile
import threading
import traceback
import uuid
import zipfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory  # noqa: E402
from werkzeug.utils import secure_filename  # noqa: E402

from ..config import Config  # noqa: E402
from ..pipeline import Pipeline  # noqa: E402
from ..report import STEPS, serialize_step  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
_RUN_LOCK = threading.Lock()          # matplotlib/pm4py không an toàn đa luồng: chạy lần lượt từng phiên


def _find_samples(root: str | None) -> dict:
    cands = [root] if root else []
    cands += [os.path.join(os.getcwd(), "data", "bpmn"),
              os.path.abspath(os.path.join(HERE, "..", "..", "..", "data", "bpmn"))]
    for c in cands:
        if c and os.path.isdir(c):
            return {os.path.basename(p): p for p in sorted(glob.glob(os.path.join(c, "*.bpmn")))}
    return {}


def create_app(work_dir: str | None = None, samples_dir: str | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
    work = work_dir or tempfile.mkdtemp(prefix="t2b_web_")
    samples = _find_samples(samples_dir)
    jobs: dict = {}

    def run_job(job, bpmn_path, cfg):
        with _RUN_LOCK:
            job["status"] = "running"
            try:
                p = Pipeline(bpmn_path, os.path.join(job["dir"], "outputs"), cfg)
                job["process"] = p.M["name"]
                for i, (key, _, _) in enumerate(STEPS, 1):
                    job["current"] = i
                    getattr(p, key)()
                    plt.close("all")
                    job["steps"].append(serialize_step(p, i))
                job["status"] = "done"
            except Exception as ex:  # báo lỗi rõ ràng cho giao diện
                job["status"] = "error"
                job["error"] = f"{type(ex).__name__}: {ex}"
                job["trace"] = traceback.format_exc(limit=4)
            finally:
                job["current"] = None
                plt.close("all")

    @app.get("/")
    def index():
        # Tệp HTML viết không có khung <html> để dùng chung cho bản trình diễn; thêm khung khi phục vụ trực tiếp.
        with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
            body = f.read()
        return Response("<!doctype html>\n<html lang=\"vi\">\n" + body + "\n</html>", mimetype="text/html")

    @app.get("/api/samples")
    def list_samples():
        return jsonify(sorted(samples))

    @app.post("/api/run")
    def start():
        jid = uuid.uuid4().hex[:10]
        jdir = os.path.join(work, jid)
        os.makedirs(os.path.join(jdir, "logs"), exist_ok=True)
        up = request.files.get("bpmn")
        if up and up.filename:
            if not up.filename.lower().endswith((".bpmn", ".xml")):
                return jsonify(error="Tệp mô hình phải có đuôi .bpmn hoặc .xml."), 400
            bpmn_path = os.path.join(jdir, secure_filename(up.filename) or "model.bpmn")
            up.save(bpmn_path)
        else:
            name = request.form.get("sample", "")
            if name not in samples:
                return jsonify(error="Chọn một tệp BPMN mẫu hoặc tải lên tệp .bpmn của bạn."), 400
            bpmn_path = os.path.join(jdir, name)
            shutil.copy(samples[name], bpmn_path)
        n_logs = 0
        for f in request.files.getlist("logs"):
            if f and f.filename and f.filename.lower().endswith((".csv", ".xes")):
                f.save(os.path.join(jdir, "logs", secure_filename(f.filename)))
                n_logs += 1

        def num(key, default, cast=int, lo=None, hi=None):
            v = request.form.get(key, "").strip()
            if not v:
                return default
            v = cast(v)
            if lo is not None:
                v = max(lo, v)
            if hi is not None:
                v = min(hi, v)
            return v

        try:
            cfg = Config(n_cases=num("n_cases", 200, int, 20, 1000), n_rep=num("n_rep", 10, int, 2, 30),
                         sla_minutes=num("sla", None, float, 1), seed=num("seed", 42, int),
                         part1_log_dir=os.path.join(jdir, "logs") if n_logs else os.path.join(jdir, "_no_logs"))
        except ValueError:
            return jsonify(error="Tham số phải là số."), 400
        job = dict(id=jid, dir=jdir, status="queued", current=None, steps=[], error=None,
                   bpmn=os.path.basename(bpmn_path), n_logs=n_logs, process=None)
        jobs[jid] = job
        threading.Thread(target=run_job, args=(job, bpmn_path, cfg), daemon=True).start()
        return jsonify(id=jid)

    @app.get("/api/job/<jid>")
    def status(jid):
        job = jobs.get(jid) or abort(404)
        return jsonify({k: v for k, v in job.items() if k != "dir"})

    @app.get("/api/job/<jid>/file/<path:name>")
    def file(jid, name):
        job = jobs.get(jid) or abort(404)
        return send_from_directory(os.path.join(job["dir"], "outputs"), name)

    @app.get("/api/job/<jid>/zip")
    def zip_all(jid):
        job = jobs.get(jid) or abort(404)
        buf = io.BytesIO()
        out = os.path.join(job["dir"], "outputs")
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in glob.glob(os.path.join(out, "*")):
                z.write(p, os.path.basename(p))
        buf.seek(0)
        stem = os.path.splitext(job["bpmn"])[0]
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"ket_qua_{stem}.zip")

    return app


def main(argv=None):
    import argparse
    import sys
    # Cố định thứ tự duyệt tập hợp để chỉ số Heuristics Miner giống báo cáo (xem __main__.py của gói).
    if os.environ.get("PYTHONHASHSEED") is None and argv is None:
        os.environ["PYTHONHASHSEED"] = "2"
        os.execv(sys.executable, [sys.executable, "-m", "text2bpmn_mining.web", *sys.argv[1:]])
    ap = argparse.ArgumentParser(prog="text2bpmn_mining.web", description="Giao diện web của pipeline Phần 2")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8050)
    a = ap.parse_args(argv)
    print(f"Mở trình duyệt tại http://{a.host}:{a.port}")
    create_app().run(host=a.host, port=a.port, debug=False, use_reloader=False, threaded=True)
