from __future__ import annotations

from datetime import date

import pandas as pd

from tests import _bootstrap  # noqa: F401
from src.config import BacktestConfig


def build_config(
    *,
    stock_pool: list[tuple[str, str]],
    start_date: str = "2024-01-02",
    end_date: str = "2024-01-05",
    initial_capital: float = 100_000,
    target_weight: float = 0.5,
    weight_tolerance: float = 0.05,
    rebalance_schedule: list[str] | None = None,
    dividend_mode: str = "reinvest",
    commission_rate: float = 0.0,
    commission_min: float = 0.0,
    stamp_tax_rate: float = 0.0,
    transfer_fee_rate: float = 0.0,
) -> BacktestConfig:
    return BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        tushare_token="",
        tushare_proxy_url="",
        cache_dir="cache",
        cache_enabled=False,
        cache_force_refresh=False,
        price_adj=None,
        initial_capital=initial_capital,
        target_weight=target_weight,
        weight_tolerance=weight_tolerance,
        rebalance_schedule=rebalance_schedule or ["01-03"],
        dividend_mode=dividend_mode,
        stock_pool=stock_pool,
        commission_rate=commission_rate,
        commission_min=commission_min,
        stamp_tax_rate=stamp_tax_rate,
        transfer_fee_rate=transfer_fee_rate,
        benchmark_index="000300.SH",
        risk_free_rate=0.02,
    )


def build_quotes(price_map: dict[str, list[float]], trading_days: list[date]) -> dict[str, pd.DataFrame]:
    return {
        code: pd.DataFrame({"date": trading_days, "close": prices})
        for code, prices in price_map.items()
    }


def build_empty_dividends(stock_codes: list[str]) -> dict[str, pd.DataFrame]:
    return {
        code: pd.DataFrame(columns=["date", "cash_dividend", "bonus_ratio", "transfer_ratio"])
        for code in stock_codes
    }


def build_benchmark(trading_days: list[date]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": trading_days,
            "close": [1000.0 + i * 5.0 for i in range(len(trading_days))],
        }
    )
