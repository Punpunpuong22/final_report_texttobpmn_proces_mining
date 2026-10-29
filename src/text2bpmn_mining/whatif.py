"""Đánh giá what-if: so sánh AS-IS với từng thay đổi và với TO-BE đầy đủ (ablation)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from .analysis import bottleneck_table, prep_events
from .bpmn import build_tobe_bpmn
from .config import Config
from .eventlog import case_table
from .simulation import simulate

CHANGES = {
    "C0": "Sửa cấu trúc BPMN (xoá luồng thừa)",
    "C1": "Thêm 1 người cho làn nghẽn",
    "C2": "Giảm 50% xác suất làm lại ở bước làm lại nhiều nhất (giả định)",
    "C3": "Tự động hoá một bước (đổi thành serviceTask)",
}


def tobe_params(changes, cfg: Config, M: dict, lane: str | None, top_rework: str | None, p_rework: float):
    cap = dict(cfg.capacity or {ln: 1 for ln in M["lanes"]})
    rwp = dict(cfg.rework_p)
    if "C1" in changes and lane:
        cap[lane] = cap.get(lane, 1) + 1
    if "C2" in changes and top_rework:
        rwp[top_rework] = 0.5 * p_rework
    return cap, rwp


def kpis(log: pd.DataFrame, sla: float) -> dict:
    ct = case_table(log, sla)
    e = prep_events(log)
    return dict(cycle_tb=ct.cycle_phut.mean(), cycle_p90=ct.cycle_phut.quantile(.9), tre_han=ct.tre_han.mean(),
                lam_viec_tb=ct.lam_viec_phut.mean(), cho_tong_tb=e.groupby("case_id").wait_m.sum().mean())


def mean_ci(x) -> str:
    return f"{x.mean():.1f} ± {1.96 * x.std(ddof=1) / math.sqrt(len(x)):.1f}"


def run_whatif(M: dict, cfg: Config, changes, sla: float, top_rework: str | None, out_dir: str, verbose=True):
    """Trả về (bảng tóm tắt trung bình ± CI 95%, bảng thô theo từng lần lặp, bảng kiểm định Wilcoxon)."""
    rows = []
    for s in [x for x in cfg.whatif_scenarios if x in cfg.scenarios]:
        sc = cfg.scenarios[s]
        btx = bottleneck_table(prep_events(simulate(M, sc, cfg, seed=cfg.seed, scenario=s)))
        lane_s = btx.loc[btx.index[0], "lane"]          # C1 nhắm làn nghẽn của CHÍNH kịch bản này
        if verbose and "C1" in changes:
            print(f"{s}: điểm nghẽn '{btx.index[0]}' → C1 thêm người cho làn {lane_s}")
        variants = [("AS-IS", ())] + [(f"chỉ {c}", (c,)) for c in changes] + \
                   [("TO-BE (" + "+".join(changes) + ")", tuple(changes))]
        for label, ch in variants:
            Mx = (build_tobe_bpmn(M, ch, out_dir, cfg.automate, cfg.repair_flows)[0]
                  if ("C0" in ch or "C3" in ch) else M)
            cap, rwp = tobe_params(ch, cfg, M, lane_s, top_rework, sc["p_rework"])
            for r in range(cfg.n_rep):
                lg = simulate(Mx, sc, cfg, seed=1000 + r, capacity=cap, rework_p=rwp, scenario=s)
                rows.append(dict(scenario=s, phuong_an=label, rep=r, **kpis(lg, sla)))
    raw = pd.DataFrame(rows)
    cols = ["cycle_tb", "cycle_p90", "tre_han", "lam_viec_tb", "cho_tong_tb"]
    summary = raw.groupby(["scenario", "phuong_an"], sort=False)[cols].agg(mean_ci)
    full = "TO-BE (" + "+".join(changes) + ")"
    tests = []
    for s in raw.scenario.unique():
        a = raw[(raw.scenario == s) & (raw.phuong_an == "AS-IS")].sort_values("rep").cycle_tb.values
        b = raw[(raw.scenario == s) & (raw.phuong_an == full)].sort_values("rep").cycle_tb.values
        p = wilcoxon(a, b).pvalue if np.any(a != b) else 1.0
        tests.append(dict(scenario=s, asis_tb=round(a.mean(), 1), tobe_tb=round(b.mean(), 1),
                          muc_giam=f"{1 - b.mean() / a.mean():.0%}", wilcoxon_p=round(float(p), 4)))
    return summary, raw, pd.DataFrame(tests)
