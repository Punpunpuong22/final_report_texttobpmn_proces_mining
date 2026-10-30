"""Chuyển kết quả từng bước của Pipeline thành JSON cho giao diện web."""
from __future__ import annotations

import math
import os

import numpy as np
import pandas as pd

STEPS = [
    ("step1_structure", "Kiểm tra cấu trúc BPMN", "BPMN có hợp lệ về hành vi (sound) không?"),
    ("step2_event_log", "Event log", "Lấy nhật ký ở đâu và nhật ký có sạch không?"),
    ("step3_describe", "Thống kê mô tả", "Quy trình chạy nhanh hay chậm, thời gian chờ chiếm bao nhiêu?"),
    ("step4_discovery", "Khám phá quy trình", "Chỉ nhìn log, quy trình thực tế trông ra sao?"),
    ("step5_conformance", "Kiểm tra tuân thủ", "Vận hành lệch khỏi BPMN ở đâu, mức nào?"),
    ("step6_bottleneck", "Điểm nghẽn", "Hồ sơ bị giữ lại ở đâu?"),
    ("step7_root_cause", "Nguyên nhân trễ hạn", "Đặc điểm nào gắn với việc trễ hạn?"),
    ("step8_tobe", "BPMN TO-BE và what-if", "Sửa gì thì tốt hơn thật, nhờ thay đổi nào?"),
]


def _cell(v):
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return "Có" if v else "Không"
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if math.isnan(v) else round(float(v), 3)
    if isinstance(v, (pd.Timestamp,)):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, (list, tuple, set)):
        return ", ".join(map(str, v)) if v else "–"
    return str(v)


def table(df: pd.DataFrame | pd.Series | None, index: bool = True, title: str = "") -> dict | None:
    if df is None:
        return None
    if isinstance(df, pd.Series):
        df = df.to_frame(df.name or "giá trị")
    d = df.reset_index() if index else df.copy()
    d.columns = [" · ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in d.columns]
    return dict(title=title, columns=list(d.columns), rows=[[_cell(v) for v in row] for row in d.itertuples(index=False)])


def _img(out, name, label):
    return dict(file=name, label=label) if os.path.exists(os.path.join(out, name)) else None


def serialize_step(p, i: int) -> dict:
    """Kết quả của bước i (1–8) ở dạng JSON, kèm kết luận ngắn."""
    key, name, question = STEPS[i - 1]
    r, out = p.r, p.out
    d = dict(n=i, key=key, name=name, question=question, tables=[], images=[], notes=[], facts=[])
    if i == 1:
        s = r["step1"]
        d["facts"] = [("Quy trình", s["name"]), ("Sound (Woflan)", "Có" if s["sound"] else "Không"),
                      ("Vấn đề cấu trúc", len(s["issues"])), ("Làn", ", ".join(p.M["lanes"]))]
        d["notes"].append("Mô hình sound: luôn kết thúc được, kết thúc sạch, bước nào cũng chạy được."
                          if s["sound"] else
                          f"Mô hình KHÔNG sound, có {len(s['issues'])} vấn đề cấu trúc: log mô phỏng sẽ chứa hành vi lạ do chính lỗi mô hình.")
        d["tables"] += [table(s["issues"], False, "Vấn đề cấu trúc") if len(s["issues"]) else None,
                        table(s["elements"], False, "Phần tử BPMN"), table(s["flows"], False, "Luồng và nhãn nhánh"),
                        table(s["traces"], False, "Một số vết mô hình cho phép (play-out 30 vết)")]
        d["images"] = [_img(out, "fig_bpmn_AS_IS.png", "BPMN AS-IS")]
    elif i == 2:
        s = r["step2"]
        d["facts"] = [("Nguồn log", s["source"]), ("Số kịch bản", len(s["scenarios"])), ("Số sự kiện", s["shape"][0]),
                      ("Số hồ sơ", int(p.events["case_id"].nunique()))]
        q = s["quality"].T
        bad = int(q[["rỗng", "end < start", "trùng"]].astype(int).values.sum())
        d["notes"].append("Không có lỗi kỹ thuật (rỗng, thời gian ngược, trùng)." if bad == 0 else f"Có {bad} dòng lỗi kỹ thuật.")
        dev = q[(q["bắt đầu sai"].astype(int) > 0) | (q["kết thúc sai/dở dang"].astype(int) > 0)]
        for sc, row in dev.iterrows():
            d["notes"].append(f"{sc}: {row['bắt đầu sai']} hồ sơ bắt đầu sai, {row['kết thúc sai/dở dang']} hồ sơ kết thúc sai.")
        cal = s.get("calib")
        if cal is not None:
            lv = cal["lam_viec"]
            vn = lambda x: f"{x:.1f}".replace(".", ",")
            d["notes"].append("Nhật ký Phần 1 chỉ có thời gian làm việc, chưa có hàng đợi. Phần 2 mô phỏng lại trên cùng BPMN và cùng "
                              "thời gian chuẩn, thêm hồ sơ đến theo thời gian và số người mỗi làn. Bảng đối chiếu là kiểm tra nhất quán giữa hai "
                              "bộ mô phỏng (chênh lệch chỉ do ngẫu nhiên), không phải kiểm chứng với thực tế.")
            lv = lv.sort_values("kich_ban_phan2")
            for sc, row in lv.iterrows():
                d["notes"].append(f"{sc} ↔ {row['kich_ban_phan2']}: làm việc {vn(row['lam_viec_text2bpmn'])} phút (Phần 1) "
                                  f"và {vn(row['lam_viec_phan2'])} phút (Phần 2), lệch {row['chenh_lech'] * 100:+.1f}%.".replace(".", ",", 1).replace(",%", "%"))
            d["facts"][0] = ("Nguồn log", "bộ mô phỏng của Phần 2 (đã đối chiếu với nhật ký Phần 1)")
            d["tables"] += [table(lv, True, "Đối chiếu thời gian làm việc mỗi hồ sơ với Phần 1"),
                            table(cal["ty_trong"], True, "Đối chiếu tỷ trọng thời gian từng bước")]
        d["tables"] += [table(q, True, "Kiểm tra chất lượng theo kịch bản"),
                        table(p.events.drop(columns=[c for c in ["arrival"] if c in p.events]).head(8), False, "8 dòng đầu của log")]
    elif i == 3:
        s = r["step3"]
        k = s["kpi"]
        worst = k["cycle_tb"].idxmax()
        d["facts"] = [("Thời hạn (giả định)", f"{s['sla']} phút"), ("Kịch bản chậm nhất", worst),
                      ("Lưu trú TB chậm nhất", f"{k.loc[worst, 'cycle_tb']:.1f} phút".replace(".", ",")),
                      ("Tỷ lệ trễ hạn", f"{k.loc[worst, 'ty_le_tre_han']:.0%}")]
        first = k.index[0]
        if k.loc[worst, "cycle_tb"] > 1.2 * k.loc[worst, "lam_viec_tb"]:
            c = lambda x: f"{x:.1f}".replace(".", ",")
            d["notes"].append(f"{worst}: làm việc {c(k.loc[worst, 'lam_viec_tb'])} phút nhưng lưu trú {c(k.loc[worst, 'cycle_tb'])} phút "
                              f"(gấp {c(k.loc[worst, 'cycle_tb'] / k.loc[first, 'cycle_tb'])} lần {first}): phần chênh là thời gian chờ.")
        else:
            d["notes"].append("Thời gian lưu trú gần bằng thời gian làm việc: hầu như không có hàng đợi.")
        # Trung bình gộp có thể đánh lừa: S2 nhiều hồ sơ dừng sớm ở nhánh ngược (ít bước) → so cùng kết quả
        if {"S1_suon_se", "S2_truc_trac"} <= set(k.index) and "ket_qua" in p.cases:
            by = p.cases.groupby(["scenario", "ket_qua"])["lam_viec_phut"].agg(["mean", "size"])
            if k.loc["S2_truc_trac", "lam_viec_tb"] < k.loc["S1_suon_se", "lam_viec_tb"]:
                d["notes"].append("S2 có thời gian làm việc trung bình thấp hơn S1 chỉ vì nhiều hồ sơ dừng sớm ở nhánh ngược (ít bước hơn); "
                                  "so cùng kết quả thì S2 chậm hơn.")
            same = [kq for kq in by.loc["S1_suon_se"].index if kq in by.loc["S2_truc_trac"].index
                    and by.loc[("S1_suon_se", kq), "size"] >= 3 and by.loc[("S2_truc_trac", kq), "size"] >= 3]
            if same:
                vn = lambda x: f"{x:.1f}".replace(".", ",")
                d["notes"].append("Làm việc theo cùng kết quả (S1 → S2): " + " · ".join(
                    f"{kq}: {vn(by.loc[('S1_suon_se', kq), 'mean'])} → {vn(by.loc[('S2_truc_trac', kq), 'mean'])} phút" for kq in same))
        d["tables"] += [table(k, True, "KPI theo kịch bản (phút)"),
                        table(s["work_share"], True, "Tỷ trọng thời gian làm việc theo bước (để đối chiếu text2BPMN)"),
                        table(s["top_variants"], False, "Top-3 biến thể mỗi kịch bản")]
        d["images"] = [_img(out, "fig_cycle_box.png", "Thời gian lưu trú theo kịch bản")]
    elif i == 4:
        s = r["step4"]
        disc = s["discovery"]
        best = disc.groupby("thuat_toan")[["pct_vet_khop", "precision"]].mean().sort_values(["pct_vet_khop", "precision"]).index[-1]
        d["facts"] = [("Thuật toán", ", ".join(disc["thuat_toan"].unique())), ("Khớp log tốt nhất", best)]
        d["notes"].append(f"{best} có % vết khớp và precision trung bình cao nhất. Đọc fitness cùng % vết khớp: "
                          "fitness cao mà % khớp thấp nghĩa là mô hình thiếu token ở hầu hết hồ sơ.")
        d["tables"] += [table(disc, False, "Chất lượng mô hình khám phá (in-sample)")]
        d["images"] = [_img(out, f"fig_dfg_{sc}.png", f"DFG {sc}") for sc in p.scen]
    elif i == 5:
        s = r["step5"]
        f = s["fitness"]
        worst = f["khop_hoan_toan"].idxmin()
        d["facts"] = [("Khớp hoàn toàn thấp nhất", f"{worst}: {f.loc[worst, 'khop_hoan_toan']:.1%}")]
        dv = s["deviations"]
        if len(dv):
            mm = dv.xs("Model move – bỏ bước", level=0).sum() if "Model move – bỏ bước" in dv.index.get_level_values(0) else None
            if mm is not None:
                d["notes"].append("Model move (bỏ bước): " + ", ".join(f"{c} {int(v)}" for c, v in mm.items() if v))
            lm = dv.xs("Log move – làm thừa/sai chỗ/làm lại", level=0).sum() if "Log move – làm thừa/sai chỗ/làm lại" in dv.index.get_level_values(0) else None
            if lm is not None:
                d["notes"].append("Log move (làm lại, làm thừa): " + ", ".join(f"{c} {int(v)}" for c, v in lm.items() if v))
        d["tables"] += [table(f, True, "Alignment với BPMN AS-IS"), table(dv, True, "Độ lệch theo bước") if len(dv) else None,
                        table(s["rule_violations"], True, "Tỷ lệ hồ sơ vi phạm luật nghiệp vụ")]
    elif i == 6:
        s = r["step6"]
        if s["has_queue"]:
            bt = s["tables"][s["hot_scenario"]]
            d["facts"] = [("Kịch bản chờ nhiều nhất", s["hot_scenario"]), ("Điểm nghẽn", s["top"]), ("Làn", s["top_lane"]),
                          ("Tỷ trọng chờ", f"{bt.loc[s['top'], 'ty_trong_cho']:.0%}")]
        else:
            d["facts"] = [("Điểm nghẽn", "Không có hàng đợi")]
            d["notes"].append("Mọi bước là việc của hệ thống hoặc năng lực dư, nên không có thời gian chờ để xếp hạng.")
        for sc, t in s["tables"].items():
            top = t.index[0]
            if t["tong_cho"].sum() > 1:
                d["notes"].append(f"{sc}: nghẽn ở {top} (làn {t.loc[top, 'lane']}), chờ TB {t.loc[top, 'cho_tb']:.1f} phút / xử lý {t.loc[top, 'xu_ly_tb']:.1f} phút; "
                                  f"tải làn: " + ", ".join(f"{k} {v:.0%}" for k, v in s["utilization"][sc].items()))
            d["tables"].append(table(t, True, f"Điểm nghẽn · {sc}"))
        d["images"] = [_img(out, "fig_wait_heatmap.png", "Thời gian chờ theo bước và kịch bản"),
                       _img(out, "fig_wait_vs_service.png", "Chờ và xử lý theo bước"),
                       _img(out, "fig_queue.png", "Hàng đợi trước bước nghẽn"), _img(out, "fig_dfg_perf.png", "DFG hiệu năng")]
    elif i == 7:
        s = r["step7"]
        d["facts"] = [("Số hồ sơ", s["n"]), ("Tỷ lệ trễ hạn", f"{s['ty_le_tre_han']:.1%}"),
                      ("Balanced accuracy", s["bal_acc"] if s["bal_acc"] is not None else "chưa đủ dữ liệu")]
        if s["importance"] is not None:
            top = s["importance"].index[0]
            d["facts"].append(("Biến quan trọng nhất", f"{top} ({s['importance'].iloc[0]:.2f})"))
            d["notes"].append("Kết quả là liên kết thống kê, không phải nhân quả; nhân quả được kiểm bằng can thiệp ở Bước 8.")
        d["tables"] += [table(s["importance"], True, "Mức quan trọng của biến"),
                        table(s["by_wip"], True, "Tỷ lệ trễ hạn theo số hồ sơ tồn lúc nộp"),
                        table(s["by_rework"], True, "Tỷ lệ trễ hạn theo số lần làm lại")]
        d["code"] = s["tree_text"]
    elif i == 8:
        s = r["step8"]
        w = s["wilcoxon"]
        d["facts"] = [("Thay đổi", " + ".join(s["changes"]) or "–"), ("BPMN TO-BE sound", "Có" if s["tobe_sound"] else "Không"),
                      ("Fitness log TO-BE", s["fitness_tobe"])]
        for _, row in w.iterrows():
            d["notes"].append(f"{row['scenario']}: lưu trú TB {row['asis_tb']} → {row['tobe_tb']} phút (giảm {row['muc_giam']}, "
                              f"Wilcoxon p = {row['wilcoxon_p']}).".replace(".", ",").rstrip(",") + ".")
        d["tables"] += [table(s["summary"], True, "AS-IS, từng thay đổi và TO-BE (trung bình ± CI 95%)"),
                        table(w, False, "Kiểm định Wilcoxon theo cặp"),
                        table(s["wait_compare"], True, f"Thời gian chờ trước và sau ({s['verify_scenario']})")]
        d["images"] = [_img(out, "fig_bpmn_TO_BE.png", "BPMN TO-BE")]
        d["downloads"] = [os.path.basename(s["tobe_path"])]
        d["legend"] = {"C0": "Sửa cấu trúc BPMN (xoá luồng thừa)", "C1": "Thêm 1 người cho làn nghẽn",
                       "C2": "Giả định giảm 50% làm lại ở bước làm lại nhiều nhất",
                       "C3": f"Tự động hoá bước {s['automate']} (đổi thành serviceTask)" if s["automate"] else "Tự động hoá một bước"}
    d["tables"] = [t for t in d["tables"] if t]
    d["images"] = [x for x in d["images"] if x]
    d["facts"] = [dict(label=a, value=_cell(b) if not isinstance(b, str) else b) for a, b in d["facts"]]
    return d
