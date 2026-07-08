"""
评价指标计算模块
"""

import numpy as np
import pandas as pd

import config as cfg


def compute_metrics(daily: pd.DataFrame, trades: list) -> dict:
    """
    根据每日净值序列和交易记录，计算全部评价指标。

    返回
    ----
    dict    指标名 → 数值（百分比已转为小数形式，展示时 ×100）
    """
    daily = daily.copy()
    total_days = len(daily)

    # ---- 日收益率 ----
    daily["nav"] = daily["total_value"] / cfg.INITIAL_CAPITAL
    daily["daily_return"] = daily["nav"].pct_change()

    # ---- 基准 ----
    has_benchmark = daily["benchmark_close"].notna().any()
    if has_benchmark:
        init_bm = daily["benchmark_close"].dropna().iloc[0]
        daily["bm_nav"] = daily["benchmark_close"] / init_bm
        daily["bm_return"] = daily["bm_nav"].pct_change()

    # 过滤掉无日收益的行
    valid = daily["daily_return"].notna()

    # ---- 累计收益率 ----
    final_nav = daily["nav"].iloc[-1]
    cumulative_return = final_nav - 1.0

    # ---- 年化收益率 ----
    years = total_days / 252
    annualized_return = (final_nav ** (1 / years)) - 1 if years > 0 else 0.0

    # ---- 年化波动率 ----
    daily_vol = daily.loc[valid, "daily_return"].std()
    annualized_vol = daily_vol * np.sqrt(252)

    # ---- 最大回撤 ----
    cummax = daily["nav"].cummax()
    drawdown = daily["nav"] / cummax - 1
    max_drawdown = drawdown.min()

    # ---- 夏普比率 ----
    excess = daily.loc[valid, "daily_return"] - cfg.RISK_FREE_RATE / 252
    sharpe = (excess.mean() / daily_vol * np.sqrt(252)) if daily_vol > 0 else 0.0

    # ---- 卡玛比率 ----
    calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    # ---- 超额收益 vs 基准 ----
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

    # ---- 交易成本合计 ----
    total_commission = sum(t.commission for t in trades)
    total_stamp_tax = sum(t.stamp_tax for t in trades)
    total_transfer_fee = sum(t.transfer_fee for t in trades)
    total_cost = total_commission + total_stamp_tax + total_transfer_fee

    # ---- 年化换手率 ----
    # 换手率 = 调仓总成交额 / 期间平均净值（单边）
    total_turnover = sum(t.amount for t in trades)
    avg_nav = daily["total_value"].mean()
    annual_turnover = (total_turnover / avg_nav) / years if years > 0 else 0.0

    # ---- 调仓统计 ----
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
        # 基准
        "基准累计收益率": bm_cumulative,
        "基准年化收益率": bm_annualized,
        "基准最大回撤": bm_max_drawdown,
        "基准年化波动率": bm_annualized_vol,
        # 交易
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
    """生成评价指标文字报告"""
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
    lines.append(f"    最终净值:        ¥{metrics['最终净值'] * cfg.INITIAL_CAPITAL:,.0f}")
    lines.append(f"    回测年数:        {metrics['回测年数']:.1f} 年")
    lines.append("")
    lines.append("=" * 52)
    return "\n".join(lines)


def annual_returns(daily: pd.DataFrame) -> pd.DataFrame:
    """计算逐年收益率"""
    daily = daily.copy()
    daily["year"] = pd.to_datetime(daily["date"]).dt.year
    daily["nav"] = daily["total_value"] / cfg.INITIAL_CAPITAL

    result = []
    for yr, grp in daily.groupby("year"):
        start_nav = grp["nav"].iloc[0]
        end_nav = grp["nav"].iloc[-1]
        ret = end_nav / start_nav - 1
        result.append({"年份": yr, "收益率": ret})

    return pd.DataFrame(result)
