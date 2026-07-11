"""
结果指标、导出与可视化。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from stock_backtest import config as cfg
from stock_backtest.models import BacktestResult

plt.rcParams["font.sans-serif"] = ["SimHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def strategy_report() -> str:
    mode_labels = {
        "value_portfolio": "价值组合",
        "equal_weight_pool": "股票池等权",
    }
    pool_names = [name for _, name, _ in cfg.UNIVERSE.stock_pool]
    industry_set = sorted({industry for _, _, industry in cfg.UNIVERSE.stock_pool if industry})
    lines = []
    lines.append("=" * 52)
    lines.append(f"{'策略运行看板':^48}")
    lines.append("=" * 52)
    lines.append("")
    lines.append("  【策略】")
    lines.append(f"    模式:            {mode_labels.get(cfg.SYSTEM.strategy_mode, cfg.SYSTEM.strategy_mode)}")
    lines.append(f"    候选池来源:      {cfg.UNIVERSE.candidate_pool_mode}")
    lines.append(f"    默认仓位方式:    等权/半等权")
    lines.append("")
    lines.append("  【回测】")
    lines.append(f"    起始日期:        {cfg.BACKTEST.start_date}")
    lines.append(f"    结束日期:        {cfg.BACKTEST.end_date}")
    lines.append(f"    初始资金:        ¥{cfg.BACKTEST.initial_capital:,.0f}")
    lines.append(f"    调仓计划:        {', '.join(cfg.BACKTEST.rebalance_schedule)}")
    lines.append(f"    基准指数:        {cfg.BACKTEST.benchmark_index}")
    lines.append("")
    lines.append("  【股票池】")
    lines.append(f"    白名单数量:      {len(cfg.UNIVERSE.stock_pool)}")
    lines.append(f"    行业数量:        {len(industry_set)}")
    lines.append(f"    持仓上限:        {cfg.STRATEGY.max_positions}")
    lines.append(f"    单股目标仓位:    {cfg.STRATEGY.target_weight * 100:.2f}%")
    lines.append(f"    单股仓位上限:    {cfg.STRATEGY.max_single_weight * 100:.2f}%")
    lines.append(f"    单行业持股上限:  {cfg.STRATEGY.max_positions_per_industry}")
    lines.append("")
    lines.append("  【规则】")
    lines.append(f"    买入增速阈值:    g > {cfg.STRATEGY.g_buy_threshold * 100:.2f}%")
    lines.append(f"    卖出增速阈值:    g < {cfg.STRATEGY.g_sell_threshold * 100:.2f}%")
    lines.append(f"    买入 PEG 阈值:   < {cfg.STRATEGY.peg_buy_threshold:.2f}")
    lines.append(f"    减仓 PEG 阈值:   >= {cfg.STRATEGY.peg_trim_threshold:.2f}")
    lines.append(f"    ROE 阈值:        >= {cfg.STRATEGY.roe_threshold * 100:.2f}%")
    lines.append(f"    换股分差阈值:    >= {cfg.STRATEGY.switch_score_gap:.2f}")
    lines.append("")
    lines.append("  【数据】")
    lines.append(f"    基本面文件:      {cfg.DATA_SOURCE.fundamental_data_path}")
    lines.append(f"    Tushare 限速:    {cfg.DATA_SOURCE.tushare_rate_limit_seconds:.2f}s")
    lines.append("")
    lines.append("  【白名单预览】")
    lines.append(f"    {', '.join(pool_names[:10])}")
    if len(pool_names) > 10:
        lines.append(f"    ... 共 {len(pool_names)} 只")
    lines.append("")
    lines.append("=" * 52)
    return "\n".join(lines)


def compute_metrics(daily: pd.DataFrame, trades: list) -> dict:
    daily = daily.copy()
    total_days = len(daily)

    daily["nav"] = daily["total_value"] / cfg.BACKTEST.initial_capital
    daily["daily_return"] = daily["nav"].pct_change()

    has_benchmark = daily["benchmark_close"].notna().any()
    if has_benchmark:
        init_bm = daily["benchmark_close"].dropna().iloc[0]
        daily["bm_nav"] = daily["benchmark_close"] / init_bm
        daily["bm_return"] = daily["bm_nav"].pct_change()

    valid = daily["daily_return"].notna()

    final_nav = daily["nav"].iloc[-1]
    cumulative_return = final_nav - 1.0

    years = total_days / 252
    annualized_return = (final_nav ** (1 / years)) - 1 if years > 0 else 0.0

    daily_vol = daily.loc[valid, "daily_return"].std()
    annualized_vol = daily_vol * np.sqrt(252)

    cummax = daily["nav"].cummax()
    drawdown = daily["nav"] / cummax - 1
    max_drawdown = drawdown.min()

    excess = daily.loc[valid, "daily_return"] - cfg.BACKTEST.risk_free_rate / 252
    sharpe = (excess.mean() / daily_vol * np.sqrt(252)) if daily_vol > 0 else 0.0

    calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    excess_return = None
    if has_benchmark:
        final_bm_nav = daily["bm_nav"].iloc[-1]
        bm_cumulative = final_bm_nav - 1.0
        bm_annualized = (final_bm_nav ** (1 / years)) - 1 if years > 0 else 0.0
        excess_return = annualized_return - bm_annualized

        bm_cummax = daily["bm_nav"].cummax()
        bm_drawdown_series = daily["bm_nav"] / bm_cummax - 1
        bm_max_drawdown = bm_drawdown_series.min()

        bm_daily_vol = daily.loc[valid, "bm_return"].std()
        bm_annualized_vol = bm_daily_vol * np.sqrt(252)
    else:
        bm_cumulative = bm_annualized = bm_max_drawdown = bm_annualized_vol = None

    total_commission = sum(t.commission for t in trades)
    total_stamp_tax = sum(t.stamp_tax for t in trades)
    total_transfer_fee = sum(t.transfer_fee for t in trades)
    total_cost = total_commission + total_stamp_tax + total_transfer_fee

    total_turnover = sum(t.amount for t in trades)
    avg_nav = daily["total_value"].mean()
    annual_turnover = (total_turnover / avg_nav) / years if years > 0 else 0.0

    rebalance_dates = set(t.date for t in trades)
    rebalance_count = len(rebalance_dates)

    return {
        "累计收益率": cumulative_return,
        "年化收益率": annualized_return,
        "年化波动率": annualized_vol,
        "最大回撤": max_drawdown,
        "夏普比率": sharpe,
        "卡玛比率": calmar,
        "超额收益(年化)": excess_return,
        "基准累计收益率": bm_cumulative,
        "基准年化收益率": bm_annualized,
        "基准最大回撤": bm_max_drawdown,
        "基准年化波动率": bm_annualized_vol,
        "总交易成本": total_cost,
        "总佣金": total_commission,
        "总印花税": total_stamp_tax,
        "总过户费": total_transfer_fee,
        "年化换手率": annual_turnover,
        "总交易笔数": len(trades),
        "调仓次数": rebalance_count,
        "最终净值": final_nav,
        "回测年数": years,
    }


def metrics_report(metrics: dict) -> str:
    def pct(v):
        if v is None:
            return "N/A"
        return f"{v * 100:.2f}%"

    lines = []
    lines.append("=" * 52)
    lines.append(f"{'回测评价指标':^48}")
    lines.append("=" * 52)
    lines.append("")
    lines.append("  【收益】")
    lines.append(f"    累计收益率:      {pct(metrics['累计收益率'])}")
    lines.append(f"    年化收益率:      {pct(metrics['年化收益率'])}")
    if metrics["超额收益(年化)"] is not None:
        lines.append(f"    超额收益(年化):  {pct(metrics['超额收益(年化)'])}")
    lines.append("")
    lines.append("  【风险】")
    lines.append(f"    年化波动率:      {pct(metrics['年化波动率'])}")
    lines.append(f"    最大回撤:        {pct(metrics['最大回撤'])}")
    lines.append("")
    lines.append("  【风险调整收益】")
    lines.append(f"    夏普比率:        {metrics['夏普比率']:.2f}")
    lines.append(f"    卡玛比率:        {metrics['卡玛比率']:.2f}")
    lines.append("")
    if metrics["基准年化收益率"] is not None:
        lines.append("  【基准对比】")
        lines.append(f"    基准年化收益率:  {pct(metrics['基准年化收益率'])}")
        lines.append(f"    基准最大回撤:    {pct(metrics['基准最大回撤'])}")
        lines.append(f"    基准年化波动率:  {pct(metrics['基准年化波动率'])}")
        lines.append("")
    lines.append("  【交易】")
    lines.append(f"    总交易成本:      ¥{metrics['总交易成本']:,.2f}")
    lines.append(f"      其中佣金:      ¥{metrics['总佣金']:,.2f}")
    lines.append(f"      其中印花税:    ¥{metrics['总印花税']:,.2f}")
    lines.append(f"      其中过户费:    ¥{metrics['总过户费']:,.2f}")
    lines.append(f"    年化换手率:      {pct(metrics['年化换手率'])}")
    lines.append(f"    总交易笔数:      {metrics['总交易笔数']}")
    lines.append(f"    调仓次数:        {metrics['调仓次数']}")
    lines.append("")
    lines.append("  【概览】")
    lines.append(f"    最终净值:        ¥{metrics['最终净值'] * cfg.BACKTEST.initial_capital:,.0f}")
    lines.append(f"    回测年数:        {metrics['回测年数']:.1f} 年")
    lines.append("")
    lines.append("=" * 52)
    return "\n".join(lines)


def annual_returns(daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    daily["year"] = pd.to_datetime(daily["date"]).dt.year
    daily["nav"] = daily["total_value"] / cfg.BACKTEST.initial_capital

    result = []
    for yr, grp in daily.groupby("year"):
        start_nav = grp["nav"].iloc[0]
        end_nav = grp["nav"].iloc[-1]
        ret = end_nav / start_nav - 1
        result.append({"年份": yr, "收益率": ret})

    return pd.DataFrame(result)


def export_backtest_result(result: BacktestResult, output_dir: Path) -> None:
    output_dir.mkdir(exist_ok=True)
    result.daily.to_csv(output_dir / "daily.csv", index=False)
    result.holdings.to_csv(output_dir / "holdings.csv", index=False)
    result.rebalance_logs.to_csv(output_dir / "rebalance_logs.csv", index=False)

    trade_rows = [
        {
            "date": trade.date,
            "code": trade.code,
            "name": trade.name,
            "action": trade.action,
            "price": trade.price,
            "shares": trade.shares,
            "amount": trade.amount,
            "commission": trade.commission,
            "stamp_tax": trade.stamp_tax,
            "transfer_fee": trade.transfer_fee,
            "reason": trade.reason,
        }
        for trade in result.trades
    ]
    pd.DataFrame(trade_rows).to_csv(output_dir / "trades.csv", index=False)


def plot_total_position_value(daily: pd.DataFrame) -> plt.Figure:
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(df["date"], df["equity_value"], color="#0b6e4f", linewidth=1.4, label="总仓位市值")

    if "total_value" in df.columns and "cash" in df.columns:
        ax.plot(
            df["date"],
            df["total_value"],
            color="#1f4e79",
            linewidth=1.0,
            linestyle="--",
            alpha=0.75,
            label="账户总资产",
        )
        ax.fill_between(df["date"], 0, df["cash"], color="#d4e6f1", alpha=0.25, label="现金")

    ax.set_title("总仓位市值变化图", fontsize=14, fontweight="bold")
    ax.set_ylabel("市值 (元)")
    ax.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def save_total_position_value_plot(daily: pd.DataFrame, output_dir: Path) -> Path:
    output_dir.mkdir(exist_ok=True)
    fig = plot_total_position_value(daily)
    output_path = output_dir / "total_position_value.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_nav_and_drawdown(daily: pd.DataFrame, trades: list) -> tuple[plt.Figure, plt.Figure]:
    daily = daily.copy()
    daily["nav"] = daily["total_value"] / cfg.BACKTEST.initial_capital

    has_bm = daily["benchmark_close"].notna().any()
    if has_bm:
        init_bm = daily["benchmark_close"].dropna().iloc[0]
        daily["bm_nav"] = daily["benchmark_close"] / init_bm

    rebalance_dates = sorted(set(t.date for t in trades))
    rebalance_navs = []
    for d in rebalance_dates:
        row = daily[daily["date"] == d]
        rebalance_navs.append(row["nav"].iloc[0] if not row.empty else None)

    fig1, ax1 = plt.subplots(figsize=(14, 6))

    ax1.plot(daily["date"], daily["nav"], color="#1a5276", linewidth=1.2, label="策略净值")
    if has_bm:
        ax1.plot(
            daily["date"],
            daily["bm_nav"],
            color="#b03a2e",
            linewidth=1.0,
            linestyle="--",
            alpha=0.8,
            label="基准净值",
        )

    valid_rd = [d for d, v in zip(rebalance_dates, rebalance_navs) if v is not None]
    valid_rn = [v for v in rebalance_navs if v is not None]
    ax1.scatter(valid_rd, valid_rn, color="#e67e22", s=18, zorder=5, label="调仓日")
    ax1.axhline(y=1.0, color="gray", linestyle=":", alpha=0.5)
    ax1.set_title("策略净值曲线", fontsize=14, fontweight="bold")
    ax1.set_ylabel("净值")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)
    fig1.autofmt_xdate()

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
        ax2.plot(daily["date"], bm_dd, color="#7f8c8d", linewidth=0.8, linestyle="--", alpha=0.7, label="基准回撤")
        ax2.legend(loc="lower left")

    ax2.set_title("回撤曲线", fontsize=14, fontweight="bold")
    ax2.set_ylabel("回撤幅度")
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax2.grid(True, alpha=0.3)
    fig2.autofmt_xdate()

    return fig1, fig2


def plot_annual_returns(annual_df: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(10, 5))

    colors = ["#27ae60" if r >= 0 else "#e74c3c" for r in annual_df["收益率"]]
    years = annual_df["年份"].astype(str)
    pct_values = annual_df["收益率"] * 100

    ax.bar(years, pct_values, color=colors, edgecolor="white", linewidth=0.5)

    for x, v in enumerate(pct_values):
        offset = 0.3 if v >= 0 else -1.0
        ax.text(x, v + offset, f"{v:.1f}%", ha="center", fontsize=9)

    ax.axhline(y=0, color="gray", linewidth=0.8)
    ax.set_title("年度收益率", fontsize=14, fontweight="bold")
    ax.set_ylabel("收益率 (%)")
    ax.grid(axis="y", alpha=0.3)
    fig.autofmt_xdate()

    return fig


def plot_holdings_heatmap(holdings: pd.DataFrame) -> plt.Figure:
    df = holdings.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["quarter"] = df["date"].dt.to_period("Q")
    quarterly = df.groupby("quarter").last().reset_index(drop=True)

    stock_cols = [c for c in quarterly.columns if c not in ("date", "quarter")]
    data = quarterly[stock_cols].T.values

    fig, ax = plt.subplots(figsize=(16, 10))
    im = ax.imshow(data, aspect="auto", cmap="YlOrRd")

    ax.set_xticks(range(len(quarterly)))
    ax.set_xticklabels([str(q) for q in quarterly["quarter"]], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(stock_cols)))
    ax.set_yticklabels([cfg.UNIVERSE.stock_name_map.get(code, code) for code in stock_cols], fontsize=8)

    ax.set_title("各股票持仓股数变化（季度末快照）", fontsize=14, fontweight="bold")
    fig.colorbar(im, ax=ax, label="持股数")
    return fig
