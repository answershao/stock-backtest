"""
回测领域模型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import pandas as pd


@dataclass
class Trade:
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
    date: date
    total_value: float
    equity_value: float
    cash: float
    benchmark_close: Optional[float] = None


@dataclass
class BacktestInputs:
    quotes: Dict[str, pd.DataFrame]
    dividends: Dict[str, pd.DataFrame]
    trade_dates: set
    benchmark_df: pd.DataFrame
    fundamentals: Optional[pd.DataFrame] = None


@dataclass
class BacktestResult:
    daily: pd.DataFrame
    trades: List[Trade]
    holdings: pd.DataFrame
    rebalance_logs: pd.DataFrame


@dataclass
class PortfolioState:
    shares: Dict[str, int]
    cash: float
    trades: List[Trade] = field(default_factory=list)


@dataclass
class MarketContext:
    start: date
    end: date
    candidate_codes: List[str]
    stock_names: Dict[str, str]
    price_index: Dict[str, Dict[date, float]]
    dividend_map: Dict[str, Dict[date, tuple]]
    benchmark_map: Dict[date, float]
    sorted_trade_dates: List[date]
    rebalance_dates: List[date]
