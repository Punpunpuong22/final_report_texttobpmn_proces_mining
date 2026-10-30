"""Đọc nhật ký của text2BPMN, chuẩn hoá cột, chuyển sang pm4py và kiểm tra chất lượng."""
from __future__ import annotations

import glob
import os

import pandas as pd
import pm4py

# Tên cột có thể gặp → tên chuẩn. Bổ sung nếu text2BPMN đặt tên khác.
COL_ALIASES = {
    "case_id": ["case_id", "case:concept:name", "case", "ma_ho_so", "caseid"],
    "activity": ["activity", "concept:name", "task", "buoc", "step"],
    "start_ts": ["start_ts", "start_timestamp", "start", "start_time", "bat_dau"],
    "end_ts": ["end_ts", "time:timestamp", "end", "end_time", "timestamp", "ket_thuc"],
    "enable_ts": ["enable_ts", "enable_time", "ready_time"],
    "resource": ["resource", "org:resource", "nguoi_thuc_hien"],
    "role": ["role", "org:role", "lane", "vai_tro"],
}


def _std_columns(df: pd.DataFrame) -> pd.DataFrame:
    low = {c.lower(): c for c in df.columns}
    ren = {}
    for std, alts in COL_ALIASES.items():
        for a in alts:
            if a.lower() in low and std not in ren.values():
                ren[low[a.lower()]] = std
                break
    return df.rename(columns=ren)


def load_part1_logs(log_dir: str | None, M: dict) -> pd.DataFrame | None:
    """Đọc mọi tệp .csv/.xes trong `log_dir`; mỗi tệp là một kịch bản (tên tệp = tên kịch bản)."""
    if not log_dir or not os.path.isdir(log_dir):
        return None
    paths = sorted(p for p in glob.glob(os.path.join(log_dir, "*")) if p.endswith((".csv", ".xes")))
    frames = []
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        raw = pm4py.read_xes(path) if path.endswith(".xes") else pd.read_csv(path)
        df = _std_columns(raw)
        if "lifecycle:transition" in df.columns:          # hai dòng start/complete → một dòng
            df["_k"] = df.groupby(["case_id", "activity", "lifecycle:transition"]).cumcount()
            st = df[df["lifecycle:transition"].str.lower() == "start"][["case_id", "activity", "_k", "end_ts"]]
            df = df[df["lifecycle:transition"].str.lower() == "complete"].merge(
                st.rename(columns={"end_ts": "start_ts"}), on=["case_id", "activity", "_k"], how="left"
            ).drop(columns="_k")
        df["scenario"] = df["scenario"] if "scenario" in df.columns else name
        frames.append(df)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    for c in ["start_ts", "end_ts", "enable_ts"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_localize(None)
    if "start_ts" not in df.columns:
        df["start_ts"] = df["end_ts"]
    df["start_ts"] = df["start_ts"].fillna(df["end_ts"])
    df["case_id"] = df["scenario"].astype(str) + "_" + df["case_id"].astype(str)
    df = df.sort_values(["case_id", "start_ts", "end_ts"])
    lane_of = {n["name"]: n["lane"] for n in M["nodes"].values()}
    type_of = {n["name"]: n["type"] for n in M["nodes"].values()}
    df["role"] = df["role"] if "role" in df.columns else df["activity"].map(lane_of).fillna("unknown")
    df["resource"] = df["resource"] if "resource" in df.columns else df["role"]
    df["task_type"] = df["activity"].map(type_of).fillna("task")
    if "enable_ts" not in df.columns:                    # xấp xỉ: sẵn sàng khi bước liền trước xong
        prev = df.groupby("case_id")["end_ts"].shift()
        df["enable_ts"] = pd.concat([prev, df["start_ts"]], axis=1).min(axis=1).fillna(df["start_ts"])
        print("⚠ Log không có enable_ts → thời gian chờ được xấp xỉ (sai khi có nhánh song song).")
    g = df.groupby("case_id")
    df["arrival"] = g["enable_ts"].transform("min")
    df["n_lam_lai"] = g["activity"].transform(lambda s: len(s) - s.nunique())
    df["ket_qua"] = g["activity"].transform("last")
    df["sai_lech"] = "không rõ"
    return df.reset_index(drop=True)


def to_pm4py(df: pd.DataFrame) -> pd.DataFrame:
    d = df.rename(columns={"case_id": "case:concept:name", "activity": "concept:name", "end_ts": "time:timestamp",
                           "start_ts": "start_timestamp", "resource": "org:resource", "role": "org:role"})
    return pm4py.format_dataframe(d, case_id="case:concept:name", activity_key="concept:name",
                                  timestamp_key="time:timestamp", start_timestamp_key="start_timestamp")


def validate_log(df: pd.DataFrame, tasks, start_tasks, end_tasks) -> dict:
    req = ["case_id", "activity", "start_ts", "end_ts"]
    first = df.sort_values("start_ts").groupby("case_id")["activity"].first()
    last = df.sort_values("end_ts").groupby("case_id")["activity"].last()
    return {"thiếu cột": [c for c in req if c not in df], "rỗng": int(df[req].isna().any(axis=1).sum()),
            "end < start": int((df.end_ts < df.start_ts).sum()),
            "trùng": int(df.duplicated(req + ["resource"]).sum()),
            "bắt đầu sai": int((~first.isin(start_tasks)).sum()),
            "kết thúc sai/dở dang": int((~last.isin(end_tasks)).sum()),
            "hoạt động lạ": sorted(set(df.activity) - set(tasks))}


def _match_scenario(name: str) -> str:
    """Kịch bản Phần 2 tương ứng với một tệp log của text2BPMN (theo tên tệp)."""
    n = name.lower()
    return "S2_truc_trac" if any(w in n for w in ("truc", "trục", "trac", "trặc", "nhieu", "nhiều")) else "S1_suon_se"


def calibration(part1: pd.DataFrame, sim: pd.DataFrame) -> dict:
    """So log text2BPMN với log mô phỏng của Phần 2 ở hai chỉ số text2BPMN hiển thị:
    thời gian làm việc mỗi hồ sơ và tỷ trọng thời gian từng bước."""
    def work(df):
        return (df.end_ts - df.start_ts).dt.total_seconds().groupby(df.case_id).sum() / 60

    def share(df):
        m = (df.end_ts - df.start_ts).dt.total_seconds().groupby(df.activity).sum()
        return m / m.sum()

    rows, shares = [], {}
    for sc, g in part1.groupby("scenario", sort=False):
        p2 = _match_scenario(str(sc))
        h = sim[sim.scenario == p2]
        w1, w2 = work(g).mean(), work(h).mean()
        rows.append(dict(log_text2bpmn=sc, kich_ban_phan2=p2, ho_so_text2bpmn=g.case_id.nunique(),
                         lam_viec_text2bpmn=round(w1, 1), lam_viec_phan2=round(w2, 1),
                         chenh_lech=round((w2 - w1) / w1, 3) if w1 else None))
        shares[f"{sc} (Phần 1)"] = share(g)
        shares[f"{p2} (Phần 2)"] = share(h)
    return dict(lam_viec=pd.DataFrame(rows).set_index("log_text2bpmn"),
                ty_trong=pd.DataFrame(shares).fillna(0).round(3))


def case_table(df: pd.DataFrame, sla: float | None = None) -> pd.DataFrame:
    """Một dòng mỗi hồ sơ: thời gian làm việc, thời gian lưu trú, biến thể, trễ hạn."""
    g = df.groupby("case_id")
    ct = g.agg(scenario=("scenario", "first"), arrival=("arrival", "first"), end=("end_ts", "max"),
               n_events=("activity", "size"))
    ct["lam_viec_phut"] = (df.end_ts - df.start_ts).dt.total_seconds().groupby(df.case_id).sum() / 60
    ct["cycle_phut"] = (ct["end"] - ct["arrival"]).dt.total_seconds() / 60
    ct["variant"] = df.sort_values(["case_id", "start_ts", "end_ts"]).groupby("case_id")["activity"].agg(" → ".join)
    for c in ["n_lam_lai", "ket_qua", "sai_lech"]:
        if c in df:
            ct[c] = g[c].first()
    if sla is not None:
        ct["tre_han"] = ct["cycle_phut"] > sla
    return ct
