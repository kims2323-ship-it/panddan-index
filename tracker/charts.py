"""차트 2장 생성: output/daily.png, output/monthly.png"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from . import env
from .metrics import Metric

from matplotlib import font_manager

_have = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams["font.family"] = next((f for f in ("AppleGothic", "Apple SD Gothic Neo", "Malgun Gothic", "NanumGothic")
                                    if f in _have), "DejaVu Sans")
plt.rcParams["axes.unicode_minus"] = False
OUT = env.ROOT / "output"
C = {"us": "#1f77b4", "kr": "#d62728", "neutral": "#555555"}
ZONES = [(0, 25, "#c0392b", "극도의 공포"), (25, 45, "#e67e22", "공포"), (45, 55, "#95a5a6", "중립"),
         (55, 75, "#82b366", "탐욕"), (75, 100, "#2e7d32", "극도의 탐욕")]


def _empty(ax, msg):
    ax.text(0.5, 0.5, msg, ha="center", va="center", transform=ax.transAxes, color="#888", fontsize=10)
    ax.set_xticks([]); ax.set_yticks([])


def _style(ax, title):
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
    ax.grid(alpha=0.25)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def daily(metrics: list[Metric], stamp: str):
    OUT.mkdir(exist_ok=True)
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)
    colors = [C["neutral"], C["us"], C["kr"]]
    for ax, m, col in zip(axes, metrics, colors):
        _style(ax, m.label)
        if not m.ok:
            _empty(ax, f"{m.label}: 데이터 없음 ({m.note})")
            continue
        s = m.series.dropna()
        if m.key == "fng":
            for lo, hi, c, _ in ZONES:
                ax.axhspan(lo, hi, color=c, alpha=0.10, lw=0)
            ax.set_ylim(0, 100)
        ax.plot(s.index, s.values, color=col, lw=1.2)
        d, v = m.latest()
        ax.scatter([d], [v], color=col, zorder=3)
        ax.annotate(f"{v:,.{m.decimals}f}", (d, v), textcoords="offset points", xytext=(-6, 8), ha="right", fontsize=9)
        if m.note != "ok":
            ax.text(0.01, 0.92, f"※ {m.note}", transform=ax.transAxes, fontsize=8, color="#b35900")
    axes[-1].xaxis.set_major_locator(mdates.YearLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.suptitle(f"일간 추적 · 공포탐욕 / S&P500 / KOSPI   ({stamp})", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    p = OUT / "daily.png"
    fig.savefig(p, dpi=130); plt.close(fig)
    return p


def monthly(metrics: list[Metric], stamp: str):
    OUT.mkdir(exist_ok=True)
    by = {m.key: m for m in metrics}
    fig, axes = plt.subplots(2, 3, figsize=(17, 8.5))
    panels = [
        ("M2 (2020-01 = 100)", ["us_m2", "kr_m2"], True),
        ("연준 자산 (조$)", ["fed"], False),
        ("미국 Shiller PE (배)", ["us_pe"], False),
        ("한국 장기과열도: KOSPI÷10년평균 (CAPE 대용)", ["kr_pe"], False),
        ("미국 버핏지수 (%)", ["bf_us"], False),
        ("한국 버핏지수 (%, 추정)", ["bf_kr"], False),
    ]
    for ax, (title, keys, rebase) in zip(axes.flat, panels):
        _style(ax, title)
        drawn = 0
        for k in keys:
            m = by[k]
            col = C["kr"] if "kr" in k else C["us"]
            if not m.ok:
                ax.plot([], [], color=col, label=f"{m.label}: 데이터 없음")
                continue
            s = m.series.dropna()
            if rebase:
                s = s / s.iloc[0] * 100
            ax.plot(s.index, s.values, color=col, lw=1.6, label=m.label)
            ax.annotate(f"{m.series.dropna().iloc[-1]:,.{m.decimals}f}{m.unit}", (s.index[-1], s.iloc[-1]),
                        textcoords="offset points", xytext=(5, 0), ha="left", va="center", fontsize=8, color=col)
            drawn += 1
        if not drawn:
            _empty(ax, "데이터 없음")
        ax.margins(x=0.14)
        ax.legend(loc="upper left", fontsize=8, frameon=False)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.suptitle(f"월간 추적 · 유동성 / 밸류에이션   ({stamp})", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    p = OUT / "monthly.png"
    fig.savefig(p, dpi=130); plt.close(fig)
    return p
