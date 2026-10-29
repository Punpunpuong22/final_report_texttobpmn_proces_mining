"""Kiểm tra nhanh (khoảng 10 giây). Chạy: `pytest -q` hoặc `python tests/test_pipeline.py`."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("PM4PY_SHOW_PROGRESS_BAR", "False")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from text2bpmn_mining import Config, Pipeline  # noqa: E402
from text2bpmn_mining.bpmn import parse_bpmn, structural_issues, to_petri, is_sound  # noqa: E402
from text2bpmn_mining.simulation import simulate  # noqa: E402

BPMN = os.path.join(ROOT, "data", "bpmn")


def test_soundness_of_sample_models():
    for name, expected in [("quy-trinh-nghi-phep", True), ("quy-trinh-tuyen-dung", True), ("quy-trinh-dat-hang", False)]:
        _, net, im, fm = to_petri(os.path.join(BPMN, name + ".bpmn"))
        assert is_sound(net, im, fm) is expected, name


def test_structural_issues_order_model():
    M = parse_bpmn(os.path.join(BPMN, "quy-trinh-dat-hang.bpmn"))
    assert len(structural_issues(M)) == 8


def test_simulation_is_reproducible():
    M = parse_bpmn(os.path.join(BPMN, "quy-trinh-nghi-phep.bpmn"))
    cfg = Config(n_cases=50)
    sc = cfg.scenarios["S1_suon_se"]
    a = simulate(M, sc, cfg, seed=7, scenario="S1")
    b = simulate(M, sc, cfg, seed=7, scenario="S1")
    assert a.equals(b) and a["case_id"].nunique() == 50


def test_full_pipeline_small(tmp_path=None):
    out = str(tmp_path) if tmp_path else os.path.join(ROOT, "outputs", "_test")
    p = Pipeline(os.path.join(BPMN, "quy-trinh-nghi-phep.bpmn"), out, Config(n_cases=60, n_rep=2))
    r = p.run(verbose=False)
    assert r["step1"]["sound"] is True
    assert set(r["step3"]["kpi"].index) == {"S1_suon_se", "S2_truc_trac", "S3_qua_tai", "S4_vi_pham"}
    assert r["step8"]["tobe_sound"] is True
    assert os.path.exists(r["step8"]["tobe_path"])


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("OK", name)
