"""
回测核心执行，包括组合账户与日频回测主循环。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Tuple

import pandas as pd

from stock_backtest import config as cfg
from stock_backtest.data import build_market_context
from stock_backtest.factors import build_factor_snapshot
from stock_backtest.models import BacktestInputs, BacktestResult, DailyRecord, PortfolioState, Trade
from stock_backtest.strategy import generate_target_weights


def round_shares(value: float) -> int:
    return int(value // 100) * 100


def calc_cost(amount: float, is_sell: bool) -> Tuple[float, float, float]:
    commission = max(amount * cfg.COSTS.commission_rate, cfg.COSTS.commission_min)
    stamp_tax = amount * cfg.COSTS.stamp_tax_rate if is_sell else 0.0
    transfer_fee = amount * cfg.COSTS.transfer_fee_rate
    return commission, stamp_tax, transfer_fee


def calc_equity_value(shares: Dict[str, int], price_index: Dict[str, Dict[date, float]], trade_date: date) -> float:
    equity_value = 0.0
    for code, held_shares in shares.items():
        price = price_index.get(code, {}).get(trade_date)
        if price is not None and price > 0 and held_shares > 0:
            equity_value += held_shares * price
    return equity_value


class PortfolioExecutor:
    def __init__(self, state: PortfolioState, price_index: Dict[str, Dict[date, float]], stock_names: Dict[str, str]):
        self.state = state
        self.price_index = price_index
        self.stock_names = stock_names

    def apply_dividend(self, trade_date: date, code: str, event: Tuple[float, float, float]) -> None:
        cash_dividend, bonus_ratio, transfer_ratio = event
        held_shares = self.state.shares.get(code, 0)
        if held_shares <= 0:
            return
        if cash_dividend > 0:
            self.state.cash += held_shares * cash_dividend
        if bonus_ratio > 0 or transfer_ratio > 0:
            self.state.shares[code] = int(held_shares * (1 + bonus_ratio + transfer_ratio))

    def portfolio_value(self, trade_date: date) -> float:
        return calc_equity_value(self.state.shares, self.price_index, trade_date) + self.state.cash

    def sell_to_target(self, trade_date: date, code: str, target_weight: float, portfolio_value: float, reason: str) -> None:
        price = self.price_index.get(code, {}).get(trade_date)
        if price is None or price <= 0:
            return
        current_shares = self.state.shares.get(code, 0)
        current_value = current_shares * price
        target_value = portfolio_value * target_weight
        excess_value = current_value - target_value
        if excess_value <= 0:
            return

        sell_shares = min(current_shares, round_shares(excess_value / price))
        if sell_shares <= 0:
            return

        amount = sell_shares * price
        commission, stamp_tax, transfer_fee = calc_cost(amount, is_sell=True)
        self.state.cash += amount - commission - stamp_tax - transfer_fee
        self.state.shares[code] -= sell_shares
        self.state.trades.append(
            Trade(
                date=trade_date,
                code=code,
                name=self.stock_names.get(code, code),
                action="SELL",
                price=price,
                shares=sell_shares,
                amount=amount,
                commission=commission,
                stamp_tax=stamp_tax,
                transfer_fee=transfer_fee,
                reason=reason,
            )
        )

    def buy_to_target(self, trade_date: date, code: str, target_weight: float, portfolio_value: float, reason: str) -> None:
        price = self.price_index.get(code, {}).get(trade_date)
        if price is None or price <= 0:
            return

        current_shares = self.state.shares.get(code, 0)
        current_value = current_shares * price
        target_value = portfolio_value * target_weight
        deficit = target_value - current_value
        if deficit <= 0:
            return

        max_affordable_shares = round_shares(
            self.state.cash / (price * (1 + cfg.COSTS.commission_rate + cfg.COSTS.transfer_fee_rate))
        )
        buy_shares = min(round_shares(deficit / price), max_affordable_shares)
        if buy_shares <= 0:
            return

        amount = buy_shares * price
        commission, _, transfer_fee = calc_cost(amount, is_sell=False)
        total_cost = amount + commission + transfer_fee
        if total_cost > self.state.cash:
            return

        self.state.cash -= total_cost
        self.state.shares[code] += buy_shares
        self.state.trades.append(
            Trade(
                date=trade_date,
                code=code,
                name=self.stock_names.get(code, code),
                action="BUY",
                price=price,
                shares=buy_shares,
                amount=amount,
                commission=commission,
                stamp_tax=0.0,
                transfer_fee=transfer_fee,
                reason=reason,
            )
        )


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
