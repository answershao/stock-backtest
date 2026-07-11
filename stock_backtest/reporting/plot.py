"""
可视化模块 — 净值曲线 + 回撤曲线
"""

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from stock_backtest.core import config as cfg

# 中文字体设置
plt.rcParams["font.sans-serif"] = ["SimHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def plot_nav_and_drawdown(daily: pd.DataFrame, trades: list) -> tuple[plt.Figure, plt.Figure]:
    """
    绘制两张图:
      1. 净值曲线（策略 vs 基准），标注调仓日
      2. 回撤曲线（策略 vs 基准）
    """
    daily = daily.copy()
    daily["nav"] = daily["total_value"] / cfg.BACKTEST.initial_capital

    has_bm = daily["benchmark_close"].notna().any()
    if has_bm:
        init_bm = daily["benchmark_close"].dropna().iloc[0]
        daily["bm_nav"] = daily["benchmark_close"] / init_bm

    # ---- 提取调仓日 ----
    rebalance_dates = sorted(set(t.date for t in trades))
    rebalance_navs = []
    for d in rebalance_dates:
        row = daily[daily["date"] == d]
        if not row.empty:
            rebalance_navs.append(row["nav"].iloc[0])
        else:
            rebalance_navs.append(None)

    # ==========================================
    # 图 1: 净值曲线
    # ==========================================
    fig1, ax1 = plt.subplots(figsize=(14, 6))

    ax1.plot(daily["date"], daily["nav"], color="#1a5276", linewidth=1.2, label="策略净值")
    if has_bm:
        ax1.plot(daily["date"], daily["bm_nav"], color="#b03a2e", linewidth=1.0,
                 linestyle="--", alpha=0.8, label="基准净值")

    # 调仓日标记
    valid_rd = [d for d, v in zip(rebalance_dates, rebalance_navs) if v is not None]
    valid_rn = [v for v in rebalance_navs if v is not None]
    ax1.scatter(valid_rd, valid_rn, color="#e67e22", s=18, zorder=5, label="调仓日")

    # 初始本金参考线
    ax1.axhline(y=1.0, color="gray", linestyle=":", alpha=0.5)

    ax1.set_title("策略净值曲线", fontsize=14, fontweight="bold")
    ax1.set_ylabel("净值")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)
    fig1.autofmt_xdate()

    # ==========================================
    # 图 2: 回撤曲线
    # ==========================================
    nav = daily["nav"].values
    cummax = np.maximum.accumulate(nav)
    dd = nav / cummax - 1

    fig2, ax2 = plt.subplots(figsize=(14, 4))

    ax2.fill_between(daily["date"], 0, dd, color="#c0392b", alpha=0.35)
    ax2.plot(daily["date"], dd, color="#c0392b", linewidth=0.8)

    if has_bm:
        bm_nav = daily["bm_nav"].values
        bm_cummax = np.maximum.accumulate(bm_nav)
        bm_dd = bm_nav / bm_cummax - 1
        ax2.plot(daily["date"], bm_dd, color="#7f8c8d", linewidth=0.8,
                 linestyle="--", alpha=0.7, label="基准回撤")
        ax2.legend(loc="lower left")

    ax2.set_title("回撤曲线", fontsize=14, fontweight="bold")
    ax2.set_ylabel("回撤幅度")
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax2.grid(True, alpha=0.3)
    fig2.autofmt_xdate()

    return fig1, fig2


def plot_annual_returns(annual_df: pd.DataFrame) -> plt.Figure:
    """绘制年度收益率柱状图"""
    fig, ax = plt.subplots(figsize=(10, 5))

    colors = ["#27ae60" if r >= 0 else "#e74c3c" for r in annual_df["收益率"]]
    years = annual_df["年份"].astype(str)
    pct_values = annual_df["收益率"] * 100

    ax.bar(years, pct_values, color=colors, edgecolor="white", linewidth=0.5)

    # 柱上标注
    for x, (yr, v) in enumerate(zip(years, pct_values)):
        offset = 0.3 if v >= 0 else -1.0
        ax.text(x, v + offset, f"{v:.1f}%", ha="center", fontsize=9)

    ax.axhline(y=0, color="gray", linewidth=0.8)
    ax.set_title("年度收益率", fontsize=14, fontweight="bold")
    ax.set_ylabel("收益率 (%)")
    ax.grid(axis="y", alpha=0.3)
    fig.autofmt_xdate()

    return fig


def plot_holdings_heatmap(holdings: pd.DataFrame) -> plt.Figure:
    """
    持仓热力图：展示各股票权重随时间的变化。
    holdings: date + 各股票代码列（股数）
    """
    # 只展示季度末，避免过密
    df = holdings.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["quarter"] = df["date"].dt.to_period("Q")
    quarterly = df.groupby("quarter").last().reset_index(drop=True)

    # 取价格估算权重（直接用日线数据太重，这里用股数替代，改为比例热力图）
    stock_cols = [c for c in quarterly.columns if c not in ("date", "quarter")]
    data = quarterly[stock_cols].T.values  # 股票 × 时间

    fig, ax = plt.subplots(figsize=(16, 10))
    im = ax.imshow(data, aspect="auto", cmap="YlOrRd")

    ax.set_xticks(range(len(quarterly)))
    ax.set_xticklabels([str(q) for q in quarterly["quarter"]], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(stock_cols)))
    ax.set_yticklabels([cfg.UNIVERSE.stock_name_map.get(code, code) for code in stock_cols], fontsize=8)

    ax.set_title("各股票持仓股数变化（季度末快照）", fontsize=14, fontweight="bold")
    fig.colorbar(im, ax=ax, label="持股数")

    return fig
