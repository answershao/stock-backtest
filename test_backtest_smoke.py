from __future__ import annotations

from datetime import date

import pandas as pd

from backtest import run_backtest
from config import BacktestConfig


def build_test_config() -> BacktestConfig:
    return BacktestConfig(
        start_date="2024-01-02",
        end_date="2024-01-05",
        tushare_token="",
        tushare_proxy_url="",
        cache_dir="cache",
        cache_enabled=False,
        cache_force_refresh=False,
        price_adj=None,
        initial_capital=100_000,
        target_weight=0.5,
        weight_tolerance=0.05,
        rebalance_schedule=["01-03"],
        dividend_mode="reinvest",
        stock_pool=[
            ("000001", "Alpha"),
            ("000002", "Beta"),
        ],
        commission_rate=0.0,
        commission_min=0.0,
        stamp_tax_rate=0.0,
        transfer_fee_rate=0.0,
        benchmark_index="000300.SH",
        risk_free_rate=0.02,
    )


def build_quotes() -> dict[str, pd.DataFrame]:
    trading_days = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    ]
    return {
        "000001": pd.DataFrame(
            {
                "date": trading_days,
                "close": [10.0, 10.5, 10.8, 11.0],
            }
        ),
        "000002": pd.DataFrame(
            {
                "date": trading_days,
                "close": [20.0, 19.5, 19.8, 20.2],
            }
        ),
    }


def build_dividends() -> dict[str, pd.DataFrame]:
    return {
        "000001": pd.DataFrame(
            columns=["date", "cash_dividend", "bonus_ratio", "transfer_ratio"]
        ),
        "000002": pd.DataFrame(
            columns=["date", "cash_dividend", "bonus_ratio", "transfer_ratio"]
        ),
    }


def build_benchmark() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 5),
            ],
            "close": [1000.0, 1005.0, 1008.0, 1010.0],
        }
    )


def main() -> None:
    config = build_test_config()
    trade_dates = {date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)}

    daily, trades, holdings, rebalance_weights = run_backtest(
        config,
        build_quotes(),
        build_dividends(),
        trade_dates,
        build_benchmark(),
    )

    assert len(daily) == 4
    assert len(holdings) == 4
    assert not rebalance_weights.empty
    assert len(trades) >= 2
    assert float(daily["total_value"].iloc[-1]) > 0
    assert set(holdings.columns) == {"date", "000001", "000002"}

    print("smoke test passed")


if __name__ == "__main__":
    main()
