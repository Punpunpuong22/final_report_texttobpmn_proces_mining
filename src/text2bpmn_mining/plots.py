"""Các biểu đồ của pipeline. Mỗi hàm lưu PNG và trả về Figure."""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def cycle_box(cases: pd.DataFrame, scenarios, sla, title: str, path: str):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.boxplot([cases[cases.scenario == s]["cycle_phut"] for s in scenarios], showfliers=True)
    ax.set_xticks(range(1, len(scenarios) + 1), scenarios)
    ax.axhline(sla, ls="--", c="crimson", lw=1, label=f"Thời hạn {sla} phút")
    ax.set_ylabel("Thời gian lưu trú (phút)")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    return fig


def wait_heatmap(ev: pd.DataFrame, scenarios, path: str):
    hm = ev.pivot_table(index="activity", columns="scenario", values="wait_m", aggfunc="mean").reindex(columns=scenarios)
    fig, ax = plt.subplots(figsize=(8, 0.6 * len(hm) + 1.5))
    im_ = ax.imshow(hm.values, cmap="Reds", aspect="auto")
    ax.set_xticks(range(len(scenarios)), scenarios, rotation=15)
    ax.set_yticks(range(len(hm)), hm.index)
    vmax = np.nanmax(hm.values) if np.isfinite(hm.values).any() else 0
    for i in range(hm.shape[0]):
        for j in range(hm.shape[1]):
            v = hm.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=9,
                        color="white" if v > vmax * 0.6 else "black")
    fig.colorbar(im_, label="Phút chờ trung bình")
    ax.set_title("Thời gian chờ trung bình theo bước và kịch bản")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    return fig


def wait_vs_service(bt: pd.DataFrame, scenario: str, path: str):
    b = bt.sort_values("cho_tb")
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(b) + 1.5))
    ax.barh(b.index, b.cho_tb, color="#d62728", label="Chờ")
    ax.barh(b.index, b.xu_ly_tb, left=b.cho_tb, color="#1f77b4", label="Xử lý")
    ax.set_xlabel("Phút (trung bình)")
    ax.set_title(f"Chờ và xử lý theo bước – {scenario}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    return fig


def queue_length(ev: pd.DataFrame, scenario: str, activity: str, path: str):
    q = ev[(ev.scenario == scenario) & (ev.activity == activity)]
    grid = pd.date_range(q.enable_ts.min(), q.start_ts.max(), freq="10min")
    fig, ax = plt.subplots(figsize=(9, 3))
    ax.plot(grid, [((q.enable_ts <= t) & (q.start_ts > t)).sum() for t in grid], lw=1)
    ax.set_ylabel("Số hồ sơ đang chờ")
    ax.set_title(f"Hàng đợi trước '{activity}' – {scenario}")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    return fig
