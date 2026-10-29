"""Mô phỏng sự kiện rời rạc dựa trên token, chạy trực tiếp trên đồ thị BPMN.

So với mô phỏng của text2BPMN, bộ mô phỏng này thêm:
  - hồ sơ đến theo quá trình Poisson và năng lực từng làn → có hàng đợi, tức có thời gian chờ;
  - ngữ nghĩa BPMN: XOR chọn một nhánh, AND tách/hợp, công việc nhiều luồng ra thì song song ngầm;
  - dấu thời gian đầy đủ: enable_ts (sẵn sàng), start_ts, end_ts, người thực hiện, làn.
Mỗi hồ sơ có dòng số ngẫu nhiên riêng (common random numbers) để so sánh AS-IS và TO-BE công bằng.
"""
from __future__ import annotations

import heapq
import math
import random
from collections import Counter
from datetime import timedelta

import pandas as pd

from .config import NEGATIVE_WORDS, POSITIVE_WORDS, SYSTEM_TYPES, TASK_TAGS, Config


def is_positive(label: str) -> bool:
    lb = label.lower()
    if any(w in lb for w in NEGATIVE_WORDS):
        return False
    return any(w in lb for w in POSITIVE_WORDS)


def branch_probs(M: dict, gw: str, p_pos: float, branch_p: dict):
    fids = M["out"][gw]
    labels = [M["flows"][f]["name"] for f in fids]
    pos = [is_positive(lb) for lb in labels]
    if any(pos) and not all(pos):
        w = [p_pos / sum(pos) if p else (1 - p_pos) / (len(pos) - sum(pos)) for p in pos]
    else:
        w = [1 / len(fids)] * len(fids)          # không nhận ra nhánh thuận → chia đều
    name = M["nodes"][gw]["name"]
    w = [branch_p.get((name, lb), x) for lb, x in zip(labels, w)]
    s = sum(w)
    return fids, [x / s for x in w]


def simulate(M: dict, sc: dict, cfg: Config, seed: int | None = None, n_cases: int | None = None,
             capacity: dict | None = None, rework_p: dict | None = None, scenario: str = "S") -> pd.DataFrame:
    """Sinh nhật ký sự kiện cho một kịch bản. Đơn vị thời gian: phút, chạy liên tục."""
    seed = cfg.seed if seed is None else seed
    n_cases = cfg.n_cases if n_cases is None else n_cases
    capacity = capacity or cfg.capacity or {lane: 1 for lane in M["lanes"]}
    rework_p = cfg.rework_p if rework_p is None else rework_p
    rng = random.Random(seed)
    N = M["nodes"]
    free = {lane: [cfg.start_time] * capacity.get(lane, 1) for lane in M["lanes"]}
    starts = [n for n in N.values() if n["type"] == "startEvent"]
    heap, seq, rows, case_info = [], 0, [], {}
    t = cfg.start_time
    for i in range(n_cases):
        t = t + timedelta(minutes=rng.expovariate(1 / sc["mean_gap"]))
        cid = f"{scenario}_{i:04d}"
        crng = random.Random(seed * 100003 + i)
        case_info[cid] = dict(case_id=cid, scenario=scenario, arrival=t, n_lam_lai=0, ket_qua=None,
                              rng=crng, joins=Counter(), steps=0)
        for s in starts:
            heapq.heappush(heap, (t, seq, cid, s["id"]))
            seq += 1
    while heap:
        t, _, cid, nid = heapq.heappop(heap)
        c = case_info[cid]
        n = N[nid]
        crng = c["rng"]
        c["steps"] += 1
        if c["steps"] > 500:                     # chặn vòng lặp vô hạn do lỗi mô hình
            continue
        nxt, t_out = list(M["out"][nid]), t
        if n["type"] in TASK_TAGS:
            reps = 1
            while crng.random() < rework_p.get(n["name"], sc["p_rework"]) and reps < 4:
                reps += 1
            c["n_lam_lai"] += reps - 1
            ready = t
            for _ in range(reps):
                mean = cfg.task_minutes.get(n["name"], cfg.default_minutes.get(n["type"], 20))
                d = crng.lognormvariate(math.log(mean) - 0.08, 0.4)
                if n["type"] in SYSTEM_TYPES:
                    st, res = ready, "Hệ thống"
                else:
                    slots = free[n["lane"]]
                    k = min(range(len(slots)), key=lambda j: slots[j])
                    st = max(ready, slots[k])
                    res = f"{n['lane']}_{k + 1}"
                en = st + timedelta(minutes=d)
                if n["type"] not in SYSTEM_TYPES:
                    free[n["lane"]][k] = en
                rows.append(dict(case_id=cid, activity=n["name"], enable_ts=ready, start_ts=st, end_ts=en,
                                 resource=res, role=n["lane"], task_type=n["type"]))
                ready = en
            t_out = ready
        elif n["type"] == "exclusiveGateway" and len(nxt) > 1:
            fids, w = branch_probs(M, nid, sc["p_positive"], cfg.branch_p)
            nxt = crng.choices(fids, weights=w)
        elif n["type"] == "parallelGateway" and len(M["inn"][nid]) > 1:
            c["joins"][nid] += 1
            if c["joins"][nid] < len(M["inn"][nid]):
                continue                         # chờ đủ nhánh mới đi tiếp
            c["joins"][nid] = 0
        elif n["type"] == "endEvent":
            c["ket_qua"] = n["name"] or "Kết thúc"
            continue
        for f in nxt:
            heapq.heappush(heap, (t_out, seq, cid, M["flows"][f]["tgt"]))
            seq += 1
    log = pd.DataFrame(rows)
    info = pd.DataFrame([{k: v for k, v in c.items() if k not in ("rng", "joins", "steps")}
                         for c in case_info.values()])
    return (log.merge(info, on="case_id", how="left")
               .sort_values(["case_id", "start_ts", "end_ts"]).reset_index(drop=True))


def inject_deviations(log: pd.DataFrame, rate: float, seed: int) -> pd.DataFrame:
    """Cài sai lệch có kiểm soát để kiểm tra bước tuân thủ có phát hiện được không:
    bỏ một bước, hoặc đảo thứ tự hai bước liền kề (đổi nhãn, giữ dấu thời gian)."""
    rng = random.Random(seed)
    log = log.copy()
    log["sai_lech"] = "none"
    drop = []
    for _, g in log.groupby("case_id"):
        if len(g) < 2 or rng.random() >= rate:
            continue
        idx = list(g.index)
        if rng.random() < 0.5:
            j = rng.choice(idx)
            drop.append(j)
            log.loc[idx, "sai_lech"] = "bo_buoc"
        else:
            j = rng.randrange(len(idx) - 1)
            a, b = idx[j], idx[j + 1]
            log.loc[[a, b], ["activity", "resource", "role"]] = log.loc[[b, a], ["activity", "resource", "role"]].values
            log.loc[idx, "sai_lech"] = "dao_thu_tu"
    return log.drop(index=drop)


def simulate_scenarios(M: dict, cfg: Config) -> pd.DataFrame:
    """Chạy mọi kịch bản trong cfg.scenarios và ghép thành một nhật ký."""
    logs = []
    for k, (name, sc) in enumerate(cfg.scenarios.items()):
        lg = simulate(M, sc, cfg, seed=cfg.seed + k, scenario=name)
        if sc.get("deviation", 0) > 0:
            lg = inject_deviations(lg, sc["deviation"], seed=cfg.seed + k)
        else:
            lg = lg.assign(sai_lech="none")
        logs.append(lg)
    return pd.concat(logs, ignore_index=True)
