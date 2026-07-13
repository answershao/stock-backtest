"""
可视化模块 — 净值曲线 + 回撤曲线
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib import font_manager
import numpy as np
import pandas as pd

from .config import BacktestConfig

def _pick_font_family() -> list[str]:
    """优先选择本机已安装的中文字体，减少 glyph 缺失告警。"""
    installed = {font.name for font in font_manager.fontManager.ttflist}
    preferred = [
        "PingFang SC",
        "Hiragino Sans GB",
        "STHeiti",
        "Heiti SC",
        "Arial Unicode MS",
        "SimHei",
        "WenQuanYi Micro Hei",
        "Noto Sans CJK SC",
    ]
    available = [name for name in preferred if name in installed]
    return available + ["DejaVu Sans"]


# 中文字体设置
plt.rcParams["font.sans-serif"] = _pick_font_family()
plt.rcParams["axes.unicode_minus"] = False


def _build_cost_profit_frame(
    quote_df: pd.DataFrame,
    stock_trades: list,
    dividend_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """构建单只股票的持仓成本和浮盈序列。"""
    df = quote_df[["date", "close"]].copy().sort_values("date").reset_index(drop=True)
    trade_map: dict = {}
    for trade in stock_trades:
        trade_map.setdefault(trade.date, []).append(trade)
    dividend_map: dict = {}
    if dividend_df is not None and not dividend_df.empty:
        for _, row in dividend_df.iterrows():
            dividend_map[row["date"]] = (
                float(row.get("bonus_ratio", 0.0)),
                float(row.get("transfer_ratio", 0.0)),
            )

    shares = 0
    cost_basis = 0.0
    avg_cost_series: list[float | None] = []
    shares_series: list[int] = []
    pnl_series: list[float | None] = []

    for trading_day, close in zip(df["date"], df["close"]):
        bonus_ratio, transfer_ratio = dividend_map.get(trading_day, (0.0, 0.0))
        if shares > 0 and (bonus_ratio > 0 or transfer_ratio > 0):
            shares = int(shares * (1 + bonus_ratio + transfer_ratio))

        for trade in trade_map.get(trading_day, []):
            if trade.action == "BUY":
                shares += trade.shares
                cost_basis += trade.amount + trade.commission + trade.transfer_fee
            elif trade.action == "SELL" and shares > 0:
                avg_cost_before_sell = cost_basis / shares if shares > 0 else 0.0
                sold_cost = avg_cost_before_sell * trade.shares
                cost_basis = max(0.0, cost_basis - sold_cost)
                shares -= trade.shares

        if shares > 0:
            avg_cost = cost_basis / shares
            market_value = shares * close
            pnl = market_value - cost_basis
        else:
            avg_cost = None
            pnl = None

        avg_cost_series.append(avg_cost)
        shares_series.append(shares)
        pnl_series.append(pnl)

    df["avg_cost"] = avg_cost_series
    df["shares"] = shares_series
    df["unrealized_pnl"] = pnl_series
    return df


def _build_position_weight_frame(
    code: str,
    quote_df: pd.DataFrame,
    holdings: pd.DataFrame,
    daily: pd.DataFrame,
) -> pd.DataFrame:
    """构建单只股票的仓位占比序列。"""
    df = quote_df[["date", "close"]].copy().sort_values("date").reset_index(drop=True)
    shares_df = holdings[["date", code]].copy().rename(columns={code: "shares"})
    total_df = daily[["date", "total_value"]].copy()
    df = df.merge(shares_df, on="date", how="left").merge(total_df, on="date", how="left")
    df["shares"] = df["shares"].fillna(0)
    df["position_value"] = df["shares"] * df["close"]
    df["position_weight"] = np.where(
        df["total_value"] > 0,
        df["position_value"] / df["total_value"],
        0.0,
    )
    return df


def _latest_stock_snapshot(cost_df: pd.DataFrame) -> dict[str, float | int | None]:
    """提取单只股票最新的持仓、成本和盈亏快照。"""
    latest_row = cost_df.iloc[-1]
    shares = int(latest_row["shares"])
    close = float(latest_row["close"])
    avg_cost = None if pd.isna(latest_row["avg_cost"]) else float(latest_row["avg_cost"])
    pnl = None if pd.isna(latest_row["unrealized_pnl"]) else float(latest_row["unrealized_pnl"])
    pnl_pct = None
    if shares > 0 and avg_cost is not None and avg_cost > 0:
        pnl_pct = close / avg_cost - 1
    return {
        "shares": shares,
        "close": close,
        "avg_cost": avg_cost,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }


def plot_nav_and_drawdown(
    config: BacktestConfig,
    daily: pd.DataFrame,
    trades: list,
) -> tuple[plt.Figure, plt.Figure]:
    """
    绘制两张图:
      1. 净值曲线（策略 vs 基准），标注调仓日
      2. 回撤曲线（策略 vs 基准）
    """
    daily = daily.copy()
    daily["nav"] = daily["total_value"] / config.initial_capital

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

    legend_style = {
        "loc": "lower center",
        "bbox_to_anchor": (0.5, 1.02),
        "ncol": 3,
        "frameon": False,
    }

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
    ax1.legend(**legend_style)
    ax1.grid(True, alpha=0.3)
    fig1.tight_layout(rect=(0, 0, 1, 0.95))
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
        ax2.legend(
            loc="lower center",
            bbox_to_anchor=(0.5, 1.02),
            ncol=1,
            frameon=False,
        )

    ax2.set_title("回撤曲线", fontsize=14, fontweight="bold")
    ax2.set_ylabel("回撤幅度")
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax2.grid(True, alpha=0.3)
    fig2.tight_layout(rect=(0, 0, 1, 0.95))
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


def plot_holdings_heatmap(config: BacktestConfig, holdings: pd.DataFrame) -> plt.Figure:
    """
    持仓热力图：展示各股票权重随时间的变化。
    holdings: date + 各股票代码列（股数）
    """
    # 只展示季度末，避免过密
    df = holdings.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["quarter"] = df["date"].dt.to_period("Q")
    quarterly = df.groupby("quarter", as_index=False).last()
    stock_name_map = config.stock_name_map

    # 取价格估算权重（直接用日线数据太重，这里用股数替代，改为比例热力图）
    stock_cols = [c for c in quarterly.columns if c not in ("date", "quarter")]
    data = quarterly[stock_cols].T.values  # 股票 × 时间

    fig, ax = plt.subplots(figsize=(16, 10))
    im = ax.imshow(data, aspect="auto", cmap="YlOrRd")

    ax.set_xticks(range(len(quarterly)))
    ax.set_xticklabels([str(q) for q in quarterly["quarter"]], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(stock_cols)))
    ax.set_yticklabels([stock_name_map.get(code, code) for code in stock_cols], fontsize=8)

    ax.set_title("各股票持仓股数变化（季度末快照）", fontsize=14, fontweight="bold")
    fig.colorbar(im, ax=ax, label="持股数")

    return fig


def plot_stock_cost_profit_panels(
    config: BacktestConfig,
    quotes: dict[str, pd.DataFrame],
    dividends: dict[str, pd.DataFrame],
    trades: list,
    holdings: pd.DataFrame,
    daily: pd.DataFrame,
    cols_per_page: int = 2,
) -> plt.Figure:
    """绘制所有股票的股价/成本/浮盈对比总图。"""
    stock_trade_map: dict[str, list] = {code: [] for code in config.stock_codes}
    for trade in trades:
        stock_trade_map.setdefault(trade.code, []).append(trade)

    chart_items: list[tuple[str, pd.DataFrame, pd.DataFrame, dict[str, float | int | None]]] = []
    for code in config.stock_codes:
        quote_df = quotes.get(code)
        if quote_df is None or quote_df.empty:
            continue
        cost_df = _build_cost_profit_frame(
            quote_df,
            stock_trade_map.get(code, []),
            dividends.get(code),
        )
        position_df = _build_position_weight_frame(code, quote_df, holdings, daily)
        snapshot = _latest_stock_snapshot(cost_df)
        chart_items.append((code, cost_df, position_df, snapshot))

    held_items = [item for item in chart_items if item[3]["shares"] > 0]
    if held_items:
        chart_items = held_items

    chart_items.sort(
        key=lambda item: (
            float("-inf") if item[3]["pnl"] is None else -float(item[3]["pnl"]),
            item[0],
        )
    )

    codes = [item[0] for item in chart_items]
    total_rows = max(1, int(np.ceil(len(codes) / cols_per_page)))
    fig_height = max(4 * total_rows, 6)
    fig, axes = plt.subplots(
        total_rows,
        cols_per_page,
        figsize=(16, fig_height),
        squeeze=False,
    )
    flat_axes = axes.flatten()

    for ax in flat_axes[len(codes):]:
        ax.axis("off")

    for ax, (code, cost_df, position_df, snapshot) in zip(flat_axes, chart_items):
        name = config.stock_name_map.get(code, code)

        ax.plot(cost_df["date"], cost_df["close"], color="#1f4e79", linewidth=1.4, label="收盘价")
        ax.plot(cost_df["date"], cost_df["avg_cost"], color="#d35400", linewidth=1.1, linestyle="--", label="持仓成本")

        valid = cost_df["avg_cost"].notna()
        profit_mask = valid & (cost_df["close"] >= cost_df["avg_cost"])
        loss_mask = valid & (cost_df["close"] < cost_df["avg_cost"])

        ax.fill_between(
            cost_df["date"],
            cost_df["close"],
            cost_df["avg_cost"],
            where=profit_mask,
            interpolate=True,
            color="#27ae60",
            alpha=0.18,
        )
        ax.fill_between(
            cost_df["date"],
            cost_df["close"],
            cost_df["avg_cost"],
            where=loss_mask,
            interpolate=True,
            color="#c0392b",
            alpha=0.18,
        )

        latest_shares = int(snapshot["shares"])
        latest_pnl = snapshot["pnl"]
        latest_pnl_pct = snapshot["pnl_pct"]
        latest_cost = snapshot["avg_cost"]
        latest_close = snapshot["close"]
        subtitle = (
            f"持股 {latest_shares:,} | 现价 ¥{latest_close:.2f} | 成本 "
            f"{'N/A' if latest_cost is None else f'¥{latest_cost:.2f}'}"
        )
        detail = (
            f"浮盈 {'N/A' if latest_pnl is None else f'¥{latest_pnl:,.0f}'}"
            f" | 收益率 {'N/A' if latest_pnl_pct is None else f'{latest_pnl_pct * 100:.1f}%'}"
        )
        ax.set_title(f"{name} ({code})\n{subtitle}\n{detail}", fontsize=10.5, fontweight="bold")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left", fontsize=8, frameon=False)

        ax2 = ax.twinx()
        pnl_series = cost_df["unrealized_pnl"].fillna(0.0)
        ax2.plot(cost_df["date"], pnl_series, color="#7f8c8d", linewidth=0.8, alpha=0.9)
        ax2.axhline(0.0, color="#7f8c8d", linewidth=0.7, linestyle=":")
        ax2.set_ylabel("浮盈(元)", fontsize=8, color="#7f8c8d")
        ax2.tick_params(axis="y", labelsize=8, colors="#7f8c8d")

        ax3 = ax.twinx()
        ax3.spines["right"].set_position(("outward", 42))
        ax3.plot(
            position_df["date"],
            position_df["position_weight"] * 100,
            color="#16a085",
            linewidth=1.0,
            linestyle="-.",
            alpha=0.95,
        )
        target_weight_pct = config.target_weight * 100
        ax3.axhline(
            target_weight_pct,
            color="#8e44ad",
            linewidth=0.9,
            linestyle="--",
            alpha=0.8,
        )
        latest_weight = float(position_df["position_weight"].iloc[-1]) * 100
        ax3.set_ylabel("仓位(%)", fontsize=8, color="#16a085")
        ax3.tick_params(axis="y", labelsize=8, colors="#16a085")
        ax3.set_ylim(bottom=0)
        ax3.text(
            0.98,
            0.04,
            f"最新仓位 {latest_weight:.1f}%",
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=8,
            color="#16a085",
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.75, "edgecolor": "none"},
        )
        ax3.text(
            0.98,
            0.14,
            f"目标仓位 {target_weight_pct:.1f}%",
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=8,
            color="#8e44ad",
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.75, "edgecolor": "none"},
        )
        ax.tick_params(axis="x", labelrotation=35, labelsize=8)
        ax.tick_params(axis="y", labelsize=8)

    title_suffix = "仅展示当前持仓" if held_items else "当前无持仓，展示全部股票"
    fig.suptitle(f"个股成本与盈利对比 ({title_suffix}, 按浮盈从高到低排序)", fontsize=14, fontweight="bold", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    return fig
