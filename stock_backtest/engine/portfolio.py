"""
组合账户执行模块
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Tuple

from stock_backtest.core import config as cfg
from stock_backtest.core.models import PortfolioState, Trade


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
