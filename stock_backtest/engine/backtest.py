"""
回测核心编排模块

当前职责：
1. 协调市场上下文、组合状态、策略信号
2. 推进日频回测循环
3. 汇总日度记录、持仓记录与调仓日志
"""
from __future__ import annotations

import pandas as pd

from stock_backtest.core import config as cfg
from stock_backtest.core.models import (
    BacktestInputs,
    BacktestResult,
    DailyRecord,
    PortfolioState,
)
from stock_backtest.data.loader import build_market_context
from stock_backtest.engine.portfolio import PortfolioExecutor, calc_equity_value
from stock_backtest.factors.factors import build_factor_snapshot
from stock_backtest.strategy.strategy import generate_target_weights


def _build_empty_logs() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["date", "code", "action", "reason", "before_weight", "after_weight", "signal_value"]
    )


def _apply_dividends_for_day(executor: PortfolioExecutor, dividend_map: dict, candidate_codes: list, trade_date) -> None:
    for code in candidate_codes:
        event = dividend_map.get(code, {}).get(trade_date)
        if event is not None:
            executor.apply_dividend(trade_date, code, event)


def _run_research_rebalance(executor, market, fundamentals, trade_date, rebalance_logs) -> None:
    if fundamentals is None or fundamentals.empty:
        raise ValueError("research_quant 模式需要 fundamentals 数据。")

    current_codes = {code for code, held in executor.state.shares.items() if held > 0}
    snapshot = build_factor_snapshot(fundamentals, trade_date, market.candidate_codes)
    target_weights, signal_table, signal_logs = generate_target_weights(snapshot, trade_date, current_codes)
    rebalance_logs.append(signal_logs)

    portfolio_value = executor.portfolio_value(trade_date)

    for code, held_shares in list(executor.state.shares.items()):
        if held_shares <= 0:
            continue
        target_weight = target_weights.get(code, 0.0)
        reason = "研究版调仓卖出"
        if code not in target_weights:
            reason = "研究版清仓"
        elif target_weight < cfg.STRATEGY.target_weight:
            reason = "研究版减仓"
        executor.sell_to_target(trade_date, code, target_weight, portfolio_value, reason)

    buy_order = []
    for code, target_weight in target_weights.items():
        row = signal_table[signal_table["code"] == code]
        score = row["score"].iloc[0] if not row.empty else float("-inf")
        buy_order.append((code, target_weight, score))
    buy_order.sort(key=lambda item: (item[2], item[0]), reverse=True)

    for code, target_weight, _ in buy_order:
        reason = "研究版新开仓" if executor.state.shares.get(code, 0) == 0 else "研究版再平衡买入"
        executor.buy_to_target(trade_date, code, target_weight, portfolio_value, reason)


def _run_static_rebalance(executor, market, trade_date) -> None:
    portfolio_value = executor.portfolio_value(trade_date)
    target_weights = {code: cfg.STRATEGY.target_weight for code in market.candidate_codes}

    for code, held_shares in list(executor.state.shares.items()):
        if held_shares > 0:
            executor.sell_to_target(trade_date, code, target_weights.get(code, 0.0), portfolio_value, "静态等权卖出")

    for code, target_weight in target_weights.items():
        executor.buy_to_target(trade_date, code, target_weight, portfolio_value, "静态等权买入")


def _record_daily_state(executor, market, trade_date, daily_records, holdings_records) -> None:
    equity_value = calc_equity_value(executor.state.shares, market.price_index, trade_date)
    total_value = equity_value + executor.state.cash
    daily_records.append(
        DailyRecord(
            date=trade_date,
            total_value=total_value,
            equity_value=equity_value,
            cash=executor.state.cash,
            benchmark_close=market.benchmark_map.get(trade_date),
        )
    )
    holdings_records.append(
        {"date": trade_date, **{code: executor.state.shares.get(code, 0) for code in market.candidate_codes}}
    )


def run_backtest(
    quotes: dict,
    dividends: dict,
    trade_dates: set,
    benchmark_df: pd.DataFrame,
    fundamentals: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list, pd.DataFrame, pd.DataFrame]:
    result = run_backtest_result(
        BacktestInputs(
            quotes=quotes,
            dividends=dividends,
            trade_dates=trade_dates,
            benchmark_df=benchmark_df,
            fundamentals=fundamentals,
        )
    )
    return result.daily, result.trades, result.holdings, result.rebalance_logs


def run_backtest_result(inputs: BacktestInputs) -> BacktestResult:
    market = build_market_context(inputs)
    executor = PortfolioExecutor(
        state=PortfolioState(
            shares={code: 0 for code in market.candidate_codes},
            cash=float(cfg.BACKTEST.initial_capital),
        ),
        price_index=market.price_index,
        stock_names=market.stock_names,
    )

    rebalance_set = set(market.rebalance_dates)
    daily_records = []
    holdings_records = []
    rebalance_logs = []

    for trade_date in market.sorted_trade_dates:
        _apply_dividends_for_day(executor, market.dividend_map, market.candidate_codes, trade_date)

        if trade_date in rebalance_set:
            if cfg.SYSTEM.strategy_mode == "research_quant":
                _run_research_rebalance(executor, market, inputs.fundamentals, trade_date, rebalance_logs)
            else:
                _run_static_rebalance(executor, market, trade_date)

        _record_daily_state(executor, market, trade_date, daily_records, holdings_records)

    daily = pd.DataFrame([record.__dict__ for record in daily_records])
    holdings = pd.DataFrame(holdings_records)
    combined_logs = pd.concat(rebalance_logs, ignore_index=True) if rebalance_logs else _build_empty_logs()

    print(f"\n  回测完成: {len(daily)} 个交易日, {len(executor.state.trades)} 笔交易")
    return BacktestResult(
        daily=daily,
        trades=executor.state.trades,
        holdings=holdings,
        rebalance_logs=combined_logs,
    )
