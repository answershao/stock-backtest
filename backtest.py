"""
回测核心引擎 — 日频模拟循环

流程：
  每日循环:
    1. 更新收盘价 → 计算市值
    2. 检查分红事件 → 入账 / 调股数
    3. 检查调仓事件 → 卖出超配、买入低配
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

import config as cfg


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Trade:
    """单笔交易记录"""
    date: date
    code: str
    name: str
    action: str          # "BUY" | "SELL"
    price: float
    shares: int           # 股数（A 股需为 100 的整数倍）
    amount: float         # 成交金额
    commission: float     # 佣金
    stamp_tax: float      # 印花税
    transfer_fee: float   # 过户费
    reason: str           # "建仓" | "调仓-超配卖出" | "调仓-低配买入"


@dataclass
class DailyRecord:
    """每日快照"""
    date: date
    total_value: float        # 总市值（含现金）
    equity_value: float       # 持仓市值
    cash: float               # 现金余额
    benchmark_close: Optional[float] = None


@dataclass
class RebalanceSnapshot:
    """单次调仓前后仓位快照。"""
    rebalance_date: date
    phase: str  # "before" | "after"
    total_value: float
    cash: float
    cash_weight: float
    stock_weights: dict[str, float] = field(default_factory=dict)


# ============================================================
# 工具函数
# ============================================================

def _round_shares(n: float) -> int:
    """A 股买卖以 100 股（1 手）为单位，向下取整"""
    return int(n // 100) * 100


def _next_trade_date(d: date, trade_dates: set[date], max_lookahead: int = 30) -> Optional[date]:
    """找到 d 之后（含）最近的交易日，最多往后找 max_lookahead 天"""
    for i in range(max_lookahead):
        candidate = d + timedelta(days=i)
        if candidate in trade_dates:
            return candidate
    return None


def _calc_cost(amount: float, is_sell: bool) -> tuple[float, float, float]:
    """
    计算交易成本，返回 (佣金, 印花税, 过户费)。
    amount: 成交金额（正数）
    """
    commission = max(amount * cfg.COMMISSION_RATE, cfg.COMMISSION_MIN)
    stamp_tax = amount * cfg.STAMP_TAX_RATE if is_sell else 0.0
    transfer_fee = amount * cfg.TRANSFER_FEE_RATE
    return commission, stamp_tax, transfer_fee


def _validate_dividend_mode(mode: str) -> str:
    """校验分红处理模式。"""
    valid_modes = {"reinvest", "cash"}
    if mode not in valid_modes:
        raise ValueError(
            f"无效的 DIVIDEND_MODE={mode!r}，可选值为 {sorted(valid_modes)}"
        )
    return mode


def _generate_rebalance_dates(start: date, end: date,
                               schedule: list[str],
                               trade_dates: set[date]) -> list[date]:
    """
    根据 REBALANCE_SCHEDULE 和交易日历生成实际调仓日列表。
    """
    # 1. 展开所有理论调仓日
    theoretical = []
    year_start = start.year
    year_end = end.year
    for y in range(year_start, year_end + 1):
        for mmdd in schedule:
            mm, dd = mmdd.split("-")
            d = date(y, int(mm), int(dd))
            theoretical.append(d)
    theoretical.sort()

    # 2. 找到 >= start 的第一个
    first_idx = None
    for i, d in enumerate(theoretical):
        if d >= start:
            first_idx = i
            break
    if first_idx is None:
        return []
    theoretical = theoretical[first_idx:]

    # 3. 截取 <= end 的
    theoretical = [d for d in theoretical if d <= end]

    # 4. 每个理论日顺延到交易日
    actual = []
    for d in theoretical:
        nd = _next_trade_date(d, trade_dates)
        if nd is not None and nd <= end:
            actual.append(nd)
    return actual


def _build_dividend_map(dividends: dict[str, pd.DataFrame]) -> dict[str, dict[date, tuple[float, float, float]]]:
    """
    构建分红事件映射表: code -> date -> (cash_per_share, bonus_ratio, transfer_ratio)
    """
    result: dict[str, dict[date, tuple[float, float, float]]] = {}
    for code, df in dividends.items():
        event_map: dict[date, tuple[float, float, float]] = {}
        for _, row in df.iterrows():
            d = row["date"]
            if isinstance(d, pd.Timestamp):
                d = d.date()
            event_map[d] = (
                float(row["cash_dividend"]),
                float(row["bonus_ratio"]),
                float(row["transfer_ratio"]),
            )
        result[code] = event_map
    return result


def _portfolio_snapshot(
    today: date,
    shares: dict[str, int],
    stock_codes: list[str],
    price_index: dict[str, dict[date, float]],
    investable_cash: float,
    dividend_cash: float,
) -> RebalanceSnapshot:
    """计算某个时点的组合仓位快照。"""
    position_values: dict[str, float] = {}
    equity_value = 0.0
    for code in stock_codes:
        px = price_index.get(code, {}).get(today)
        value = shares[code] * px if (px is not None and px > 0) else 0.0
        position_values[code] = value
        equity_value += value

    cash = investable_cash + dividend_cash
    total_value = equity_value + cash
    if total_value > 0:
        stock_weights = {code: position_values[code] / total_value for code in stock_codes}
        cash_weight = cash / total_value
    else:
        stock_weights = {code: 0.0 for code in stock_codes}
        cash_weight = 0.0

    return RebalanceSnapshot(
        rebalance_date=today,
        phase="",
        total_value=total_value,
        cash=cash,
        cash_weight=cash_weight,
        stock_weights=stock_weights,
    )


# ============================================================
# 回测主函数
# ============================================================

def run_backtest(
    quotes: dict[str, pd.DataFrame],
    dividends: dict[str, pd.DataFrame],
    trade_dates: set[date],
    benchmark_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[Trade], pd.DataFrame, pd.DataFrame]:
    """
    执行回测。

    返回
    ----
    daily_records : DataFrame  每日净值序列
    trades : list[Trade]       所有交易记录
    holdings : DataFrame       每只股票每日持仓股数
    rebalance_weights : DataFrame  每次调仓前后仓位占比
    """
    # ---- 初始化 ----
    start = date.fromisoformat(cfg.START_DATE)
    end = date.fromisoformat(cfg.END_DATE)
    dividend_mode = _validate_dividend_mode(cfg.DIVIDEND_MODE)

    # 调仓日列表
    rebalance_dates = _generate_rebalance_dates(start, end, cfg.REBALANCE_SCHEDULE, trade_dates)
    rebalance_set = set(rebalance_dates)
    print(f"  调仓日: {[str(d) for d in rebalance_dates]}")
    if not rebalance_dates:
        raise RuntimeError("回测区间内没有可执行的调仓日")

    # 分红事件表
    div_map = _build_dividend_map(dividends)

    # 价格索引: code -> {date: close_price}
    price_index: dict[str, dict[date, float]] = {}
    for code, df in quotes.items():
        price_index[code] = dict(zip(df["date"], df["close"]))

    # 初始状态
    shares: dict[str, int] = {code: 0 for code in cfg.STOCK_CODES}
    investable_cash = float(cfg.INITIAL_CAPITAL)
    dividend_cash = 0.0
    trades: list[Trade] = []
    daily_records: list[DailyRecord] = []
    holdings_records: list[dict] = []  # 每日持仓股数
    rebalance_snapshots: list[RebalanceSnapshot] = []
    pending_initial_buys = set(cfg.STOCK_CODES)

    # 基准指数
    benchmark_map: dict[date, float] = {}
    if not benchmark_df.empty:
        benchmark_map = dict(zip(benchmark_df["date"], benchmark_df["close"]))

    # 排序的交易日列表
    sorted_trade_dates = sorted([d for d in trade_dates if start <= d <= end])

    if not sorted_trade_dates:
        raise RuntimeError("回测区间内无交易日数据")

    initial_trade_date = sorted_trade_dates[0]

    stock_codes = cfg.STOCK_CODES
    stock_names = dict(cfg.STOCK_POOL)
    target_weight = cfg.TARGET_WEIGHT
    upper = target_weight + cfg.WEIGHT_TOLERANCE  # 5.1%
    lower = target_weight - cfg.WEIGHT_TOLERANCE  # 4.9%
    target_value_per = float(cfg.INITIAL_CAPITAL) * target_weight

    # ---- 日频循环 ----
    for today in sorted_trade_dates:
        # ---- Step 1: 计算当日持仓市值 ----
        equity_value = 0.0
        for code in stock_codes:
            px = price_index.get(code, {}).get(today)
            if px is not None and px > 0:
                equity_value += shares[code] * px
        cash = investable_cash + dividend_cash
        total_value = equity_value + cash

        # ---- Step 2: 处理分红事件 ----
        for code in stock_codes:
            events = div_map.get(code, {})
            if today in events:
                cash_div, bonus_r, trans_r = events[today]
                s = shares[code]
                if s > 0:
                    # 现金分红入账
                    if cash_div > 0:
                        dividend_amount = s * cash_div
                        if dividend_mode == "reinvest":
                            investable_cash += dividend_amount
                        else:
                            dividend_cash += dividend_amount
                    # 送股 / 转增
                    if bonus_r > 0 or trans_r > 0:
                        new_s = int(s * (1 + bonus_r + trans_r))
                        shares[code] = new_s

        # ---- Step 3: 处理调仓 ----
        if pending_initial_buys:
            for code in list(pending_initial_buys):
                px = price_index.get(code, {}).get(today)
                if px is None or px <= 0:
                    continue
                target_shares = _round_shares(target_value_per / px)
                if target_shares <= 0:
                    pending_initial_buys.discard(code)
                    continue
                buy_amount = target_shares * px
                comm, _, trans = _calc_cost(buy_amount, is_sell=False)
                total_cost = buy_amount + comm + trans
                if total_cost > investable_cash:
                    continue
                investable_cash -= total_cost
                shares[code] += target_shares
                pending_initial_buys.discard(code)
                reason = "建仓" if today == initial_trade_date else "补建仓"
                trades.append(Trade(
                    date=today, code=code, name=stock_names.get(code, ""),
                    action="BUY", price=px, shares=target_shares,
                    amount=buy_amount, commission=comm, stamp_tax=0.0,
                    transfer_fee=trans, reason=reason,
                ))

        if today in rebalance_set:
            before_snapshot = _portfolio_snapshot(
                today,
                shares,
                stock_codes,
                price_index,
                investable_cash,
                dividend_cash,
            )
            before_snapshot.phase = "before"
            rebalance_snapshots.append(before_snapshot)

            is_first_buy = all(shares[c] == 0 for c in stock_codes)

            if not is_first_buy:
                # 权重复平衡
                rebalance_total_value = before_snapshot.total_value
                current_values = {
                    code: before_snapshot.stock_weights[code] * rebalance_total_value
                    for code in stock_codes
                }

                # --- 阶段一：卖出超配 ---
                for code in stock_codes:
                    px = price_index.get(code, {}).get(today)
                    if px is None or px <= 0:
                        continue
                    cur_val = current_values[code]
                    cur_weight = cur_val / rebalance_total_value if rebalance_total_value > 0 else 0.0
                    if cur_weight > upper:
                        # 卖出超出目标的部分
                        target_val = rebalance_total_value * target_weight
                        sell_amount = cur_val - target_val
                        sell_shares = _round_shares(sell_amount / px)
                        if sell_shares <= 0:
                            continue
                        actual_amount = sell_shares * px
                        comm, stamp, trans = _calc_cost(actual_amount, is_sell=True)
                        investable_cash += actual_amount - comm - stamp - trans
                        shares[code] -= sell_shares
                        trades.append(Trade(
                            date=today, code=code, name=stock_names.get(code, ""),
                            action="SELL", price=px, shares=sell_shares,
                            amount=actual_amount, commission=comm, stamp_tax=stamp,
                            transfer_fee=trans, reason="调仓-超配卖出",
                        ))

                # --- 阶段二：买入低配 ---
                # 重新算一次总市值（卖出后现金变了）
                equity_value = 0.0
                for code in stock_codes:
                    px = price_index.get(code, {}).get(today)
                    if px and px > 0:
                        equity_value += shares[code] * px
                cash = investable_cash + dividend_cash
                rebalance_total_value = equity_value + cash

                # 收集低配股票
                underweight = []
                for code in stock_codes:
                    px = price_index.get(code, {}).get(today)
                    if px is None or px <= 0:
                        continue
                    cur_val = shares[code] * px
                    cur_weight = cur_val / rebalance_total_value if rebalance_total_value > 0 else 0.0
                    if cur_weight < lower:
                        target_val = rebalance_total_value * target_weight
                        deficit = target_val - cur_val
                        if deficit > 0:
                            underweight.append((code, px, deficit))

                # 按缺额比例分配可用现金
                total_deficit = sum(d for _, _, d in underweight)
                available_cash = investable_cash  # 可用于买入的现金

                for code, px, deficit in underweight:
                    if total_deficit > 0:
                        alloc = available_cash * (deficit / total_deficit)
                    else:
                        alloc = 0.0
                    alloc = min(alloc, deficit)  # 不超买
                    buy_shares = _round_shares(alloc / px)
                    if buy_shares <= 0:
                        continue
                    buy_amount = buy_shares * px
                    comm, _, trans = _calc_cost(buy_amount, is_sell=False)
                    total_cost = buy_amount + comm + trans
                    if total_cost <= investable_cash:
                        investable_cash -= total_cost
                        shares[code] += buy_shares
                        trades.append(Trade(
                            date=today, code=code, name=stock_names.get(code, ""),
                            action="BUY", price=px, shares=buy_shares,
                            amount=buy_amount, commission=comm, stamp_tax=0.0,
                            transfer_fee=trans, reason="调仓-低配买入",
                        ))

                after_snapshot = _portfolio_snapshot(
                    today,
                    shares,
                    stock_codes,
                    price_index,
                    investable_cash,
                    dividend_cash,
                )
                after_snapshot.phase = "after"
                rebalance_snapshots.append(after_snapshot)

        # ---- Step 4: 记录当日快照 ----
        # 重新计算最终市值
        equity_value = 0.0
        for code in stock_codes:
            px = price_index.get(code, {}).get(today)
            if px is not None and px > 0:
                equity_value += shares[code] * px
        cash = investable_cash + dividend_cash
        total_value = equity_value + cash

        bm_close = benchmark_map.get(today)
        daily_records.append(DailyRecord(
            date=today,
            total_value=total_value,
            equity_value=equity_value,
            cash=cash,
            benchmark_close=bm_close,
        ))

        # 记录持仓
        holdings_records.append({
            "date": today,
            **{code: shares[code] for code in stock_codes},
        })

    # ---- 构建输出 ----
    df_daily = pd.DataFrame([
        {
            "date": r.date,
            "total_value": r.total_value,
            "equity_value": r.equity_value,
            "cash": r.cash,
            "benchmark_close": r.benchmark_close,
        }
        for r in daily_records
    ])

    df_holdings = pd.DataFrame(holdings_records)
    df_rebalance = pd.DataFrame(
        [
            {
                "rebalance_date": snap.rebalance_date,
                "phase": snap.phase,
                "total_value": snap.total_value,
                "cash": snap.cash,
                "cash_weight": snap.cash_weight,
                **{f"{code}_weight": snap.stock_weights.get(code, 0.0) for code in stock_codes},
            }
            for snap in rebalance_snapshots
        ]
    )

    print(f"\n  回测完成: {len(df_daily)} 个交易日, {len(trades)} 笔交易")
    return df_daily, trades, df_holdings, df_rebalance
