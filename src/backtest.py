"""
回测核心引擎。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from .config import BacktestConfig


@dataclass
class Trade:
    """单笔交易记录。"""

    date: date
    code: str
    name: str
    action: str
    price: float
    shares: int
    amount: float
    commission: float
    stamp_tax: float
    transfer_fee: float
    reason: str


@dataclass
class DailyRecord:
    """每日快照。"""

    date: date
    total_value: float
    equity_value: float
    cash: float
    benchmark_close: float | None = None


@dataclass
class RebalanceSnapshot:
    """单次调仓前后仓位快照。"""

    rebalance_date: date
    phase: str
    total_value: float
    cash: float
    cash_weight: float
    stock_weights: dict[str, float] = field(default_factory=dict)


@dataclass
class BacktestState:
    """回测过程中的可变状态。"""

    shares: dict[str, int]
    investable_cash: float
    dividend_cash: float
    pending_initial_buys: set[str]
    trades: list[Trade] = field(default_factory=list)
    daily_records: list[DailyRecord] = field(default_factory=list)
    holdings_records: list[dict] = field(default_factory=list)
    rebalance_snapshots: list[RebalanceSnapshot] = field(default_factory=list)


@dataclass(frozen=True)
class MarketDataIndex:
    """回测过程使用的市场数据索引。"""

    price_index: dict[str, dict[date, float]]
    dividend_map: dict[str, dict[date, tuple[float, float, float]]]
    benchmark_map: dict[date, float]

    def price_on(self, code: str, trading_day: date) -> float | None:
        return self.price_index.get(code, {}).get(trading_day)


@dataclass(frozen=True)
class RebalancePolicy:
    """回测中的调仓规则。"""

    stock_codes: list[str]
    stock_names: dict[str, str]
    rebalance_set: set[date]
    target_weight: float
    upper_weight: float
    lower_weight: float
    target_value_per_stock: float
    initial_trade_date: date


@dataclass(frozen=True)
class BacktestContext:
    """封装回测执行过程中会反复读取的上下文。"""

    config: BacktestConfig
    market: MarketDataIndex
    policy: RebalancePolicy


def _round_shares(n: float) -> int:
    """A 股买卖以 100 股为单位，向下取整。"""
    return int(n // 100) * 100


def _next_trade_date(d: date, trade_dates: set[date], max_lookahead: int = 30) -> date | None:
    """找到 d 之后最近的交易日。"""
    for i in range(max_lookahead):
        candidate = d + timedelta(days=i)
        if candidate in trade_dates:
            return candidate
    return None


def _calc_cost(config: BacktestConfig, amount: float, is_sell: bool) -> tuple[float, float, float]:
    """计算交易成本。"""
    commission = max(amount * config.commission_rate, config.commission_min)
    stamp_tax = amount * config.stamp_tax_rate if is_sell else 0.0
    transfer_fee = amount * config.transfer_fee_rate
    return commission, stamp_tax, transfer_fee


def _validate_dividend_mode(mode: str) -> str:
    """校验分红处理模式。"""
    valid_modes = {"reinvest", "cash"}
    if mode not in valid_modes:
        raise ValueError(f"无效的 DIVIDEND_MODE={mode!r}，可选值为 {sorted(valid_modes)}")
    return mode


def _generate_rebalance_dates(
    start: date,
    end: date,
    schedule: list[str],
    trade_dates: set[date],
) -> list[date]:
    """根据调仓计划生成实际调仓日。"""
    theoretical: list[date] = []
    for year in range(start.year, end.year + 1):
        for mmdd in schedule:
            month, day = mmdd.split("-")
            theoretical.append(date(year, int(month), int(day)))

    actual: list[date] = []
    for scheduled in sorted(d for d in theoretical if start <= d <= end):
        trade_day = _next_trade_date(scheduled, trade_dates)
        if trade_day is not None and trade_day <= end:
            actual.append(trade_day)
    return actual


def _build_dividend_map(
    dividends: dict[str, pd.DataFrame],
) -> dict[str, dict[date, tuple[float, float, float]]]:
    """构建分红事件映射表。"""
    result: dict[str, dict[date, tuple[float, float, float]]] = {}
    for code, df in dividends.items():
        event_map: dict[date, tuple[float, float, float]] = {}
        for _, row in df.iterrows():
            event_date = row["date"]
            if isinstance(event_date, pd.Timestamp):
                event_date = event_date.date()
            event_map[event_date] = (
                float(row["cash_dividend"]),
                float(row["bonus_ratio"]),
                float(row["transfer_ratio"]),
            )
        result[code] = event_map
    return result


def _build_price_index(quotes: dict[str, pd.DataFrame]) -> dict[str, dict[date, float]]:
    """构建按股票和日期索引的收盘价字典。"""
    return {
        code: dict(zip(df["date"], df["close"]))
        for code, df in quotes.items()
    }


def _build_benchmark_map(benchmark_df: pd.DataFrame) -> dict[date, float]:
    """构建基准价格索引。"""
    if benchmark_df.empty:
        return {}
    return dict(zip(benchmark_df["date"], benchmark_df["close"]))


def _create_backtest_context(
    config: BacktestConfig,
    quotes: dict[str, pd.DataFrame],
    dividends: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame,
    rebalance_dates: list[date],
    sorted_trade_dates: list[date],
) -> BacktestContext:
    """构建回测执行上下文。"""
    stock_codes = config.stock_codes
    stock_names = config.stock_name_map
    target_weight = config.target_weight
    return BacktestContext(
        config=config,
        market=MarketDataIndex(
            price_index=_build_price_index(quotes),
            dividend_map=_build_dividend_map(dividends),
            benchmark_map=_build_benchmark_map(benchmark_df),
        ),
        policy=RebalancePolicy(
            stock_codes=stock_codes,
            stock_names=stock_names,
            rebalance_set=set(rebalance_dates),
            target_weight=target_weight,
            upper_weight=target_weight + config.weight_tolerance,
            lower_weight=target_weight - config.weight_tolerance,
            target_value_per_stock=float(config.initial_capital) * target_weight,
            initial_trade_date=sorted_trade_dates[0],
        ),
    )


def _calculate_equity_value(
    today: date,
    shares: dict[str, int],
    context: BacktestContext,
) -> float:
    """计算当日持仓市值。"""
    equity_value = 0.0
    for code in context.policy.stock_codes:
        px = context.market.price_on(code, today)
        if px is not None and px > 0:
            equity_value += shares[code] * px
    return equity_value


def _portfolio_snapshot(
    today: date,
    state: BacktestState,
    context: BacktestContext,
) -> RebalanceSnapshot:
    """计算某个时点的组合仓位快照。"""
    position_values: dict[str, float] = {}
    equity_value = 0.0
    for code in context.policy.stock_codes:
        px = context.market.price_on(code, today)
        value = state.shares[code] * px if (px is not None and px > 0) else 0.0
        position_values[code] = value
        equity_value += value

    cash = state.investable_cash + state.dividend_cash
    total_value = equity_value + cash
    if total_value > 0:
        stock_weights = {
            code: position_values[code] / total_value for code in context.policy.stock_codes
        }
        cash_weight = cash / total_value
    else:
        stock_weights = {code: 0.0 for code in context.policy.stock_codes}
        cash_weight = 0.0

    return RebalanceSnapshot(
        rebalance_date=today,
        phase="",
        total_value=total_value,
        cash=cash,
        cash_weight=cash_weight,
        stock_weights=stock_weights,
    )


def _record_daily_snapshot(
    today: date,
    context: BacktestContext,
    state: BacktestState,
) -> None:
    """记录每日资产快照和持仓。"""
    equity_value = _calculate_equity_value(today, state.shares, context)
    cash = state.investable_cash + state.dividend_cash
    total_value = equity_value + cash

    state.daily_records.append(
        DailyRecord(
            date=today,
            total_value=total_value,
            equity_value=equity_value,
            cash=cash,
            benchmark_close=context.market.benchmark_map.get(today),
        )
    )
    state.holdings_records.append(
        {"date": today, **{code: state.shares[code] for code in context.policy.stock_codes}}
    )


def _build_output_frames(
    state: BacktestState,
    context: BacktestContext,
) -> tuple[pd.DataFrame, list[Trade], pd.DataFrame, pd.DataFrame]:
    """构建回测输出 DataFrame。"""
    df_daily = pd.DataFrame(
        [
            {
                "date": record.date,
                "total_value": record.total_value,
                "equity_value": record.equity_value,
                "cash": record.cash,
                "benchmark_close": record.benchmark_close,
            }
            for record in state.daily_records
        ]
    )
    df_holdings = pd.DataFrame(state.holdings_records)
    df_rebalance = pd.DataFrame(
        [
            {
                "rebalance_date": snap.rebalance_date,
                "phase": snap.phase,
                "total_value": snap.total_value,
                "cash": snap.cash,
                "cash_weight": snap.cash_weight,
                **{
                    f"{code}_weight": snap.stock_weights.get(code, 0.0)
                    for code in context.policy.stock_codes
                },
            }
            for snap in state.rebalance_snapshots
        ]
    )
    return df_daily, state.trades, df_holdings, df_rebalance


def _apply_dividends(
    today: date,
    state: BacktestState,
    dividend_mode: str,
    context: BacktestContext,
) -> None:
    """处理当日分红送转。"""
    for code in context.policy.stock_codes:
        events = context.market.dividend_map.get(code, {})
        if today not in events:
            continue
        cash_div, bonus_r, trans_r = events[today]
        current_shares = state.shares[code]
        if current_shares <= 0:
            continue

        if cash_div > 0:
            dividend_amount = current_shares * cash_div
            if dividend_mode == "reinvest":
                state.investable_cash += dividend_amount
            else:
                state.dividend_cash += dividend_amount

        if bonus_r > 0 or trans_r > 0:
            state.shares[code] = int(current_shares * (1 + bonus_r + trans_r))


def _record_trade(
    state: BacktestState,
    today: date,
    code: str,
    context: BacktestContext,
    action: str,
    price: float,
    shares: int,
    amount: float,
    commission: float,
    stamp_tax: float,
    transfer_fee: float,
    reason: str,
) -> None:
    """记录一笔交易。"""
    state.trades.append(
        Trade(
            date=today,
            code=code,
            name=context.policy.stock_names.get(code, ""),
            action=action,
            price=price,
            shares=shares,
            amount=amount,
            commission=commission,
            stamp_tax=stamp_tax,
            transfer_fee=transfer_fee,
            reason=reason,
        )
    )


def _execute_initial_buys(
    context: BacktestContext,
    today: date,
    state: BacktestState,
) -> None:
    """执行首批建仓或补建仓。"""
    for code in list(state.pending_initial_buys):
        px = context.market.price_on(code, today)
        if px is None or px <= 0:
            continue

        target_shares = _round_shares(context.policy.target_value_per_stock / px)
        if target_shares <= 0:
            state.pending_initial_buys.discard(code)
            continue

        buy_amount = target_shares * px
        comm, _, trans = _calc_cost(context.config, buy_amount, is_sell=False)
        total_cost = buy_amount + comm + trans
        if total_cost > state.investable_cash:
            continue

        state.investable_cash -= total_cost
        state.shares[code] += target_shares
        state.pending_initial_buys.discard(code)
        reason = "建仓" if today == context.policy.initial_trade_date else "补建仓"
        _record_trade(
            state,
            today,
            code,
            context,
            "BUY",
            px,
            target_shares,
            buy_amount,
            comm,
            0.0,
            trans,
            reason,
        )


def _sell_overweight_positions(
    context: BacktestContext,
    today: date,
    state: BacktestState,
    before_snapshot: RebalanceSnapshot,
) -> None:
    """卖出超配仓位。"""
    rebalance_total_value = before_snapshot.total_value
    current_values = {
        code: before_snapshot.stock_weights[code] * rebalance_total_value
        for code in context.policy.stock_codes
    }

    for code in context.policy.stock_codes:
        px = context.market.price_on(code, today)
        if px is None or px <= 0:
            continue

        cur_val = current_values[code]
        cur_weight = cur_val / rebalance_total_value if rebalance_total_value > 0 else 0.0
        if cur_weight <= context.policy.upper_weight:
            continue

        target_val = rebalance_total_value * context.policy.target_weight
        sell_amount = cur_val - target_val
        sell_shares = _round_shares(sell_amount / px)
        if sell_shares <= 0:
            continue

        actual_amount = sell_shares * px
        comm, stamp, trans = _calc_cost(context.config, actual_amount, is_sell=True)
        state.investable_cash += actual_amount - comm - stamp - trans
        state.shares[code] -= sell_shares
        _record_trade(
            state,
            today,
            code,
            context,
            "SELL",
            px,
            sell_shares,
            actual_amount,
            comm,
            stamp,
            trans,
            "调仓-超配卖出",
        )


def _buy_underweight_positions(
    context: BacktestContext,
    today: date,
    state: BacktestState,
) -> None:
    """买入低配仓位。"""
    equity_value = _calculate_equity_value(today, state.shares, context)
    cash = state.investable_cash + state.dividend_cash
    rebalance_total_value = equity_value + cash

    underweight: list[tuple[str, float, float]] = []
    for code in context.policy.stock_codes:
        px = context.market.price_on(code, today)
        if px is None or px <= 0:
            continue

        cur_val = state.shares[code] * px
        cur_weight = cur_val / rebalance_total_value if rebalance_total_value > 0 else 0.0
        if cur_weight >= context.policy.lower_weight:
            continue

        target_val = rebalance_total_value * context.policy.target_weight
        deficit = target_val - cur_val
        if deficit > 0:
            underweight.append((code, px, deficit))

    total_deficit = sum(deficit for _, _, deficit in underweight)
    available_cash = state.investable_cash

    for code, px, deficit in underweight:
        alloc = available_cash * (deficit / total_deficit) if total_deficit > 0 else 0.0
        alloc = min(alloc, deficit)
        buy_shares = _round_shares(alloc / px)
        if buy_shares <= 0:
            continue

        buy_amount = buy_shares * px
        comm, _, trans = _calc_cost(context.config, buy_amount, is_sell=False)
        total_cost = buy_amount + comm + trans
        if total_cost > state.investable_cash:
            continue

        state.investable_cash -= total_cost
        state.shares[code] += buy_shares
        _record_trade(
            state,
            today,
            code,
            context,
            "BUY",
            px,
            buy_shares,
            buy_amount,
            comm,
            0.0,
            trans,
            "调仓-低配买入",
        )


def _rebalance_if_needed(
    context: BacktestContext,
    today: date,
    state: BacktestState,
) -> None:
    """在调仓日执行再平衡。"""
    if today not in context.policy.rebalance_set:
        return

    before_snapshot = _portfolio_snapshot(today, state, context)
    before_snapshot.phase = "before"
    state.rebalance_snapshots.append(before_snapshot)

    is_first_buy = all(state.shares[code] == 0 for code in context.policy.stock_codes)
    if is_first_buy:
        return

    _sell_overweight_positions(
        context,
        today,
        state,
        before_snapshot,
    )
    _buy_underweight_positions(
        context,
        today,
        state,
    )

    after_snapshot = _portfolio_snapshot(today, state, context)
    after_snapshot.phase = "after"
    state.rebalance_snapshots.append(after_snapshot)


def run_backtest(
    config: BacktestConfig,
    quotes: dict[str, pd.DataFrame],
    dividends: dict[str, pd.DataFrame],
    trade_dates: set[date],
    benchmark_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[Trade], pd.DataFrame, pd.DataFrame]:
    """执行回测。"""
    start = date.fromisoformat(config.start_date)
    end = date.fromisoformat(config.end_date)
    dividend_mode = _validate_dividend_mode(config.dividend_mode)

    rebalance_dates = _generate_rebalance_dates(
        start,
        end,
        config.rebalance_schedule,
        trade_dates,
    )
    print(f"  调仓日: {[str(d) for d in rebalance_dates]}")
    if not rebalance_dates:
        raise RuntimeError("回测区间内没有可执行的调仓日")

    sorted_trade_dates = sorted(d for d in trade_dates if start <= d <= end)
    if not sorted_trade_dates:
        raise RuntimeError("回测区间内无交易日数据")

    context = _create_backtest_context(
        config,
        quotes,
        dividends,
        benchmark_df,
        rebalance_dates,
        sorted_trade_dates,
    )

    state = BacktestState(
        shares={code: 0 for code in context.policy.stock_codes},
        investable_cash=float(config.initial_capital),
        dividend_cash=0.0,
        pending_initial_buys=set(context.policy.stock_codes),
    )

    for today in sorted_trade_dates:
        _apply_dividends(today, state, dividend_mode, context)
        if state.pending_initial_buys:
            _execute_initial_buys(
                context,
                today,
                state,
            )
        _rebalance_if_needed(
            context,
            today,
            state,
        )
        _record_daily_snapshot(today, context, state)

    df_daily, trades, df_holdings, df_rebalance = _build_output_frames(state, context)
    print(f"\n  回测完成: {len(df_daily)} 个交易日, {len(trades)} 笔交易")
    return df_daily, trades, df_holdings, df_rebalance
