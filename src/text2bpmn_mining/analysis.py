"""Khám phá, tuân thủ, điểm nghẽn và nguyên nhân trễ hạn."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

import pandas as pd
import pm4py

from .eventlog import case_table, to_pm4py

ALGOS = ("Alpha", "Heuristics (0.9)", "Inductive (IMf 0.2)")


# ---------------------------------------------------------------- Khám phá
def discover(events: pd.DataFrame, scenarios, out_dir: str | None = None) -> pd.DataFrame:
    """DFG, Alpha Miner, Heuristics Miner và Inductive Miner cho từng kịch bản, kèm bốn chỉ số chất lượng (in-sample).

    - Alpha: dựng quan hệ footprint (→, ||, #) từ DFG rồi tạo place cho các cặp tập (A, B) với A → B.
      Không xử lý được vòng lặp độ dài 1 và nhiễu.
    - Heuristics: giữ cạnh a→b khi độ phụ thuộc (|a>b|−|b>a|)/(|a>b|+|b>a|+1) ≥ 0,9;
      vòng lặp a→a khi |a>a|/(|a>a|+1) ≥ 0,9. Chịu nhiễu, không bảo đảm sound.
    - Inductive (IMf): chia log đệ quy theo cắt tuần tự / lựa chọn / song song / vòng lặp,
      lọc cạnh hiếm (< 20% cạnh mạnh nhất). Luôn sound.
    """
    rows = []
    for s in scenarios:
        L = to_pm4py(events[events.scenario == s])
        if out_dir:
            dfg, sa, ea = pm4py.discover_dfg(L)
            pm4py.save_vis_dfg(dfg, sa, ea, f"{out_dir}/fig_dfg_{s}.png", rankdir="TB")
        for algo in ALGOS:
            if algo.startswith("Alpha"):
                net, im, fm = pm4py.discover_petri_net_alpha(L)
            elif algo.startswith("Heuristics"):
                net, im, fm = pm4py.discover_petri_net_heuristics(L, dependency_threshold=0.9)
            else:
                net, im, fm = pm4py.discover_petri_net_inductive(L, noise_threshold=0.2)
            fit = pm4py.fitness_token_based_replay(L, net, im, fm)
            rows.append(dict(scenario=s, thuat_toan=algo, fitness=round(fit["log_fitness"], 3),
                             pct_vet_khop=round(fit["perc_fit_traces"], 1),
                             precision=round(pm4py.precision_token_based_replay(L, net, im, fm), 3),
                             generalization=round(pm4py.generalization_tbr(L, net, im, fm), 3),
                             simplicity=round(pm4py.simplicity_petri_net(net, im, fm), 3)))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Tuân thủ
def align_by_variant(df: pd.DataFrame, net, im, fm):
    """Alignment tính một lần cho mỗi biến thể rồi nhân theo số hồ sơ (nhanh hơn nhiều)."""
    ct = case_table(df)
    variants = ct["variant"].value_counts()
    vlog = pd.DataFrame([dict(case_id=f"v{i:05d}", activity=a, end_ts=datetime(2026, 1, 1) + timedelta(minutes=j))
                         for i, v in enumerate(variants.index) for j, a in enumerate(v.split(" → "))])
    vlog["start_ts"] = vlog["end_ts"]
    L = pm4py.convert_to_event_log(to_pm4py(vlog))
    al = pm4py.conformance_diagnostics_alignments(L, net, im, fm, multi_processing=False)
    vid = {f"v{i:05d}": v for i, v in enumerate(variants.index)}
    fit, dev = {}, Counter()
    for tr, r in zip(L, al):
        v = vid[tr.attributes["concept:name"]]
        fit[v] = r["fitness"]
        for lm, mm in r["alignment"]:
            if lm != ">>" and mm == ">>":
                dev[("Log move – làm thừa/sai chỗ/làm lại", lm)] += variants[v]
            elif lm == ">>" and mm not in (None, ">>"):
                dev[("Model move – bỏ bước", mm)] += variants[v]
    ct["fitness"] = ct["variant"].map(fit)
    return ct, pd.DataFrame([dict(loai=k[0], hoat_dong=k[1], so_lan=n) for k, n in dev.items()])


def rule_checks(df: pd.DataFrame, ct: pd.DataFrame, rules) -> pd.DataFrame:
    """Mỗi cột là một luật, True = hồ sơ tuân thủ."""
    out = pd.DataFrame(index=ct.index)
    acts = df.sort_values(["case_id", "start_ts"]).groupby("case_id")["activity"].apply(list)
    res = df.groupby(["case_id", "activity"])["resource"].apply(set)
    for r in list(rules) + [("khong_lam_lai",), ("dung_han",)]:
        if r[0] == "truoc":
            a, b = r[1], r[2]
            out[f"{a} trước {b}"] = acts.map(lambda s, a=a, b=b: b not in s or a in s[:s.index(b)])
        elif r[0] == "khac_nguoi":
            a, b = r[1], r[2]
            out[f"{a} ≠ người {b}"] = [not (res.get((c, a), set()) & res.get((c, b), set())) for c in ct.index]
        elif r[0] == "khong_lam_lai":
            out["Không làm lại"] = acts.map(lambda s: len(s) == len(set(s)))
        elif r[0] == "dung_han" and "tre_han" in ct:
            out["Đúng hạn"] = ~ct["tre_han"]
    return out


# ---------------------------------------------------------------- Hiệu năng
def prep_events(df: pd.DataFrame) -> pd.DataFrame:
    e = df.copy()
    e["wait_m"] = ((e.start_ts - e.enable_ts).dt.total_seconds() / 60).clip(lower=0)
    e["service_m"] = (e.end_ts - e.start_ts).dt.total_seconds() / 60
    return e


def bottleneck_table(e: pd.DataFrame) -> pd.DataFrame:
    """Xếp hạng bước theo TỔNG thời gian chờ (không theo thời gian làm việc)."""
    t = e.groupby("activity").agg(lane=("role", "first"), tan_suat=("case_id", "size"), cho_tb=("wait_m", "mean"),
                                  cho_p90=("wait_m", lambda x: x.quantile(.9)), xu_ly_tb=("service_m", "mean"),
                                  tong_cho=("wait_m", "sum"), tong_xu_ly=("service_m", "sum"))
    t["ty_trong_cho"] = t.tong_cho / t.tong_cho.sum() if t.tong_cho.sum() else 0
    t["ty_trong_lam_viec"] = t.tong_xu_ly / t.tong_xu_ly.sum()
    return t.sort_values("tong_cho", ascending=False).round(2)


def utilization(e: pd.DataFrame, capacity: dict) -> pd.Series:
    span = (e.end_ts.max() - e.enable_ts.min()).total_seconds() / 60
    u = e[e.resource != "Hệ thống"].groupby("role")["service_m"].sum() / (span * pd.Series(capacity))
    return u.dropna().sort_values(ascending=False).round(2)


# ---------------------------------------------------------------- Nguyên nhân
def wip_at_arrival(ct: pd.DataFrame) -> pd.Series:
    """Số hồ sơ đang tồn trong hệ thống lúc mỗi hồ sơ được nộp."""
    out = pd.Series(0, index=ct.index)
    for _, g in ct.groupby("scenario"):
        arr, end = g["arrival"].values, g["end"].values
        out.loc[g.index] = [int(((arr < a) & (end > a)).sum()) for a in arr]
    return out


def root_cause(cases: pd.DataFrame, seed: int) -> dict:
    """Cây quyết định nông (CART) cho biến trễ hạn. Kết quả là liên kết thống kê, không phải nhân quả."""
    from sklearn.metrics import balanced_accuracy_score
    from sklearn.model_selection import train_test_split
    from sklearn.tree import DecisionTreeClassifier, export_text

    rc = cases[cases.sai_lech.isin(["none", "không rõ"])].copy()   # bỏ hồ sơ bị cài sai lệch
    rc["ton_luc_nop"] = wip_at_arrival(rc)
    X = pd.get_dummies(rc[["n_lam_lai", "ton_luc_nop", "ket_qua"]], drop_first=True).astype(float)
    y = rc["tre_han"].astype(int)
    res = dict(n=len(rc), ty_le_tre_han=round(float(y.mean()), 3), tree_text=None, importance=None, bal_acc=None)
    if y.value_counts().min() >= 10 and y.nunique() == 2:
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.3, stratify=y, random_state=seed)
        tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=10, class_weight="balanced",
                                      random_state=seed).fit(Xtr, ytr)
        res["bal_acc"] = round(balanced_accuracy_score(yte, tree.predict(Xte)), 3)
        res["tree_text"] = export_text(tree, feature_names=list(X.columns))
        res["importance"] = pd.Series(tree.feature_importances_, X.columns).sort_values(ascending=False).round(3)
    res["by_rework"] = rc.groupby("n_lam_lai")["tre_han"].agg(["mean", "size"]).round(2)
    res["by_wip"] = rc.groupby(pd.cut(rc.ton_luc_nop, [-1, 2, 5, 10, 20, 1000]), observed=False)["tre_han"] \
                      .agg(["mean", "size"]).round(2)
    return res
