"""Pipeline tám bước, chạy được từng bước (notebook) hoặc một lần (dòng lệnh).

    p = Pipeline("data/bpmn/quy-trinh-nghi-phep.bpmn")
    p.step1_structure(); p.step2_event_log(); ... ; p.step8_tobe()
hoặc
    Pipeline("...").run()
"""
from __future__ import annotations

import os

import pandas as pd
import pm4py

from . import analysis, bpmn, eventlog, plots, simulation, whatif
from .config import Config

os.environ.setdefault("PM4PY_SHOW_PROGRESS_BAR", "False")


class Pipeline:
    def __init__(self, bpmn_path: str, out_dir: str | None = None, cfg: Config | None = None):
        self.bpmn_path = bpmn_path
        stem = os.path.splitext(os.path.basename(bpmn_path))[0]
        self.out = out_dir or os.path.join("outputs", stem)
        os.makedirs(self.out, exist_ok=True)
        self.M = bpmn.parse_bpmn(bpmn_path)
        self.cfg = (cfg or Config()).resolve(self.M["name"])
        if self.cfg.part1_log_dir is None:
            self.cfg.part1_log_dir = os.path.join("data", "part1_logs", stem)
        if self.cfg.capacity is None:
            self.cfg.capacity = {lane: 1 for lane in self.M["lanes"]}
        self.r: dict = {}

    def _p(self, name: str) -> str:
        return os.path.join(self.out, name)

    # ------------------------------------------------------------ Bước 1
    def step1_structure(self) -> dict:
        """Đọc BPMN, kiểm tra soundness (Woflan) và các lỗi cấu trúc."""
        M = self.M
        bpmn_obj, net, im, fm = bpmn.to_petri(self.bpmn_path)
        self.net, self.im, self.fm = net, im, fm
        issues = bpmn.structural_issues(M)
        issues.to_csv(self._p("tab_bpmn_structure.csv"), index=False)
        pm4py.save_vis_bpmn(bpmn_obj, self._p("fig_bpmn_AS_IS.png"))
        self.start_tasks, self.end_tasks = bpmn.start_end_tasks(M)
        self.r["step1"] = dict(name=M["name"], elements=bpmn.element_table(M), flows=bpmn.flow_table(M),
                               sound=bpmn.is_sound(net, im, fm), issues=issues,
                               traces=bpmn.sample_traces(net, im, fm))
        return self.r["step1"]

    # ------------------------------------------------------------ Bước 2
    def step2_event_log(self) -> dict:
        """Ưu tiên log của text2BPMN; nếu chưa có thì mô phỏng bốn kịch bản trên chính BPMN."""
        part1 = eventlog.load_part1_logs(self.cfg.part1_log_dir, self.M)
        calib = None
        if part1 is not None and self.cfg.part1_logs_as != "doi_chieu":
            self.events, self.source = part1, f"nhật ký có sẵn ({part1['scenario'].nunique()} tệp)"
        else:
            self.events, self.source = simulation.simulate_scenarios(self.M, self.cfg), "bộ mô phỏng của Phần 2"
            if part1 is not None:
                self.source += " (đã đối chiếu với log text2BPMN)"
                calib = eventlog.calibration(part1, self.events)
                for k, t in calib.items():
                    t.to_csv(self._p(f"tab_doi_chieu_{k}.csv"))
        self.scen = list(dict.fromkeys(self.events["scenario"]))
        self.events.to_csv(self._p("event_log_all.csv"), index=False)
        pm4py.write_xes(eventlog.to_pm4py(self.events.drop(columns=["arrival"])), self._p("event_log_all.xes"))
        quality = pd.DataFrame({s: eventlog.validate_log(self.events[self.events.scenario == s], self.M["tasks"],
                                                         self.start_tasks, self.end_tasks) for s in self.scen})
        self.r["step2"] = dict(source=self.source, scenarios=self.scen, shape=self.events.shape, quality=quality,
                               calib=calib)
        return self.r["step2"]

    # ------------------------------------------------------------ Bước 3
    def step3_describe(self) -> dict:
        """KPI theo kịch bản, tỷ trọng thời gian làm việc từng bước, biến thể phổ biến."""
        ev, scen = self.events, self.scen
        c0 = eventlog.case_table(ev)
        self.sla = self.cfg.sla_minutes or round(1.5 * c0[c0.scenario == scen[0]]["cycle_phut"].quantile(0.9))
        self.cases = eventlog.case_table(ev, self.sla)
        cs = self.cases
        kpi = cs.groupby("scenario").agg(
            so_ho_so=("n_events", "size"), so_bien_the=("variant", "nunique"),
            lam_viec_tb=("lam_viec_phut", "mean"), cycle_tb=("cycle_phut", "mean"),
            cycle_p90=("cycle_phut", lambda x: x.quantile(.9)), ty_le_tre_han=("tre_han", "mean"),
            lam_lai_tb=("n_lam_lai", "mean")).reindex(scen).round(2)
        kpi.to_csv(self._p("tab_kpi.csv"))
        share = ev.assign(m=(ev.end_ts - ev.start_ts).dt.total_seconds() / 60).pivot_table(
            index="activity", columns="scenario", values="m", aggfunc="sum")
        share = (share / share.sum()).round(2).reindex(columns=scen)
        top_variants = pd.concat([cs[cs.scenario == s]["variant"].value_counts(normalize=True).head(3)
                                  .rename("ty_le").reset_index().assign(scenario=s) for s in scen], ignore_index=True)
        fig = plots.cycle_box(cs, scen, self.sla, f"{self.M['name']}: thời gian lưu trú theo kịch bản",
                              self._p("fig_cycle_box.png"))
        self.r["step3"] = dict(sla=self.sla, kpi=kpi, work_share=share, top_variants=top_variants, fig=fig)
        return self.r["step3"]

    # ------------------------------------------------------------ Bước 4
    def step4_discovery(self) -> dict:
        """DFG, Alpha Miner, Heuristics Miner, Inductive Miner và bốn chỉ số chất lượng."""
        disc = analysis.discover(self.events, self.scen, self.out)
        disc.to_csv(self._p("tab_discovery.csv"), index=False)
        self.r["step4"] = dict(discovery=disc, dfg_images=[self._p(f"fig_dfg_{s}.png") for s in self.scen])
        return self.r["step4"]

    # ------------------------------------------------------------ Bước 5
    def step5_conformance(self) -> dict:
        """Alignment với BPMN AS-IS và kiểm tra luật nghiệp vụ."""
        conf, devs = [], []
        for s in self.scen:
            ct, dv = analysis.align_by_variant(self.events[self.events.scenario == s], self.net, self.im, self.fm)
            conf.append(ct)
            devs.append(dv.assign(scenario=s))
        conf, devs = pd.concat(conf), pd.concat(devs)
        fit = conf.groupby("scenario").agg(fitness_tb=("fitness", "mean"),
                                           khop_hoan_toan=("fitness", lambda x: (x >= 0.9999).mean())
                                           ).reindex(self.scen).round(3)
        dev_tab = (devs.pivot_table(index=["loai", "hoat_dong"], columns="scenario", values="so_lan", fill_value=0)
                   if len(devs) else pd.DataFrame())
        rules = analysis.rule_checks(self.events, self.cases, self.cfg.rules)
        viol = (~rules).groupby(self.cases["scenario"]).mean().reindex(self.scen).round(3)
        fit.to_csv(self._p("tab_alignment.csv"))
        viol.to_csv(self._p("tab_rule_violations.csv"))
        self.r["step5"] = dict(fitness=fit, deviations=dev_tab, rule_violations=viol)
        return self.r["step5"]

    # ------------------------------------------------------------ Bước 6
    def step6_bottleneck(self) -> dict:
        """Thời gian chờ, mức tải từng làn và điểm nghẽn."""
        ev = self.ev = analysis.prep_events(self.events)
        tables = {s: analysis.bottleneck_table(ev[ev.scenario == s]) for s in self.scen}
        util = {s: analysis.utilization(ev[ev.scenario == s], self.cfg.capacity) for s in self.scen}
        pd.concat(tables).to_csv(self._p("tab_bottleneck.csv"))
        self.s_hot = ev.groupby("scenario")["wait_m"].sum().idxmax()
        bt = tables[self.s_hot]
        self.top, self.top_lane = bt.index[0], bt.loc[bt.index[0], "lane"]
        self.has_queue = bt.tong_cho.sum() > 1
        figs = [plots.wait_heatmap(ev, self.scen, self._p("fig_wait_heatmap.png")),
                plots.wait_vs_service(bt, self.s_hot, self._p("fig_wait_vs_service.png"))]
        if self.has_queue:
            figs.append(plots.queue_length(ev, self.s_hot, self.top, self._p("fig_queue.png")))
        pdfg, sa, ea = pm4py.discover_performance_dfg(eventlog.to_pm4py(self.events[self.events.scenario == self.s_hot]))
        pm4py.save_vis_performance_dfg(pdfg, sa, ea, self._p("fig_dfg_perf.png"), rankdir="TB")
        self.r["step6"] = dict(tables=tables, utilization=util, hot_scenario=self.s_hot, top=self.top,
                               top_lane=self.top_lane, has_queue=self.has_queue, figs=figs)
        return self.r["step6"]

    # ------------------------------------------------------------ Bước 7
    def step7_root_cause(self) -> dict:
        """Cây quyết định cho biến trễ hạn (liên kết, không phải nhân quả)."""
        self.r["step7"] = analysis.root_cause(self.cases, self.cfg.seed)
        return self.r["step7"]

    # ------------------------------------------------------------ Bước 8
    def step8_tobe(self) -> dict:
        """BPMN TO-BE, so sánh what-if có kiểm định và vòng kiểm chứng."""
        cfg, M = self.cfg, self.M
        s_rework = self.cases.groupby("scenario")["n_lam_lai"].mean().idxmax()
        rw = self.ev[self.ev.scenario == s_rework].groupby(["case_id", "activity"]).size()
        self.top_rework = (rw[rw > 1] - 1).groupby(level=1).sum().idxmax() if (rw > 1).any() else None
        changes = [c for c in ["C0", "C1", "C2", "C3"]
                   if (c != "C0" or cfg.repair_flows) and (c != "C3" or cfg.automate) and (c != "C1" or self.has_queue)]
        self.changes = changes
        M_tobe, tobe_path = bpmn.build_tobe_bpmn(M, changes, self.out, cfg.automate, cfg.repair_flows)
        bpmn_tobe, net_tb, im_tb, fm_tb = bpmn.to_petri(tobe_path)
        pm4py.save_vis_bpmn(bpmn_tobe, self._p("fig_bpmn_TO_BE.png"))
        summary, raw, tests = whatif.run_whatif(M, cfg, changes, self.sla, self.top_rework, self.out)
        summary.to_csv(self._p("tab_asis_vs_tobe_ablation.csv"))
        tests.to_csv(self._p("tab_wilcoxon.csv"), index=False)
        # Vòng kiểm chứng: log sinh từ TO-BE đối chiếu với chính BPMN TO-BE; điểm nghẽn có dịch chuyển không
        s_ver = self.s_hot if self.s_hot in cfg.scenarios else "S3_qua_tai"
        sc = cfg.scenarios[s_ver]
        cap, rwp = whatif.tobe_params(changes, cfg, M, self.top_lane, self.top_rework, sc["p_rework"])
        lg_tb = simulation.simulate(M_tobe, sc, cfg, seed=1000, capacity=cap, rework_p=rwp, scenario=s_ver)
        lg_as = simulation.simulate(M, sc, cfg, seed=1000, scenario=s_ver)
        fit_tobe = round(float(analysis.align_by_variant(lg_tb, net_tb, im_tb, fm_tb)[0].fitness.mean()), 4)
        wait_cmp = pd.DataFrame({
            "AS-IS chờ TB (phút)": analysis.bottleneck_table(analysis.prep_events(lg_as)).cho_tb,
            "TO-BE chờ TB (phút)": analysis.bottleneck_table(analysis.prep_events(lg_tb)).cho_tb}).round(1)
        self.r["step8"] = dict(changes=changes, top_rework=self.top_rework, automate=cfg.automate,
                               repair_flows=cfg.repair_flows, tobe_path=tobe_path,
                               tobe_sound=bpmn.is_sound(net_tb, im_tb, fm_tb), summary=summary, raw=raw,
                               wilcoxon=tests, verify_scenario=s_ver, fitness_tobe=fit_tobe, wait_compare=wait_cmp)
        return self.r["step8"]

    # ------------------------------------------------------------ Chạy hết
    def run(self, verbose: bool = True) -> dict:
        import matplotlib
        matplotlib.use("Agg")
        steps = [self.step1_structure, self.step2_event_log, self.step3_describe, self.step4_discovery,
                 self.step5_conformance, self.step6_bottleneck, self.step7_root_cause, self.step8_tobe]
        for i, f in enumerate(steps, 1):
            if verbose:
                print(f"[{i}/8] {f.__doc__.strip().splitlines()[0] if f.__doc__ else f.__name__}")
            f()
        if verbose:
            self.print_summary()
        return self.r

    def print_summary(self):
        r = self.r
        print(f"\n=== {r['step1']['name']} ({self.bpmn_path}) ===")
        print(f"Sound: {r['step1']['sound']} | vấn đề cấu trúc: {len(r['step1']['issues'])}")
        print(f"Nguồn log: {r['step2']['source']} | thời hạn: {r['step3']['sla']} phút")
        print(r["step3"]["kpi"].to_string())
        print(f"Điểm nghẽn ({r['step6']['hot_scenario']}): {r['step6']['top']} – làn {r['step6']['top_lane']}")
        print(r["step8"]["wilcoxon"].to_string(index=False))
        print(f"TO-BE sound: {r['step8']['tobe_sound']} | đầu ra: {self.out}")
