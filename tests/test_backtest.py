from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from tests import _bootstrap  # noqa: F401
from src.backtest import run_backtest
from src.metrics import compute_metrics
from src.plot import _build_cost_profit_frame
from tests.helpers import (
    build_benchmark,
    build_config,
    build_empty_dividends,
    build_quotes,
)


class BacktestEngineTest(unittest.TestCase):
    def test_basic_backtest_outputs_expected_shapes(self) -> None:
        trading_days = [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
            date(2024, 1, 5),
        ]
        config = build_config(
            stock_pool=[("000001", "Alpha"), ("000002", "Beta")],
        )
        daily, trades, holdings, rebalance_weights = run_backtest(
            config,
            build_quotes(
                {
                    "000001": [10.0, 10.5, 10.8, 11.0],
                    "000002": [20.0, 19.5, 19.8, 20.2],
                },
                trading_days,
            ),
            build_empty_dividends(config.stock_codes),
            set(trading_days),
            build_benchmark(trading_days),
        )

        self.assertEqual(len(daily), 4)
        self.assertEqual(len(holdings), 4)
        self.assertFalse(rebalance_weights.empty)
        self.assertGreaterEqual(len(trades), 2)
        self.assertGreater(float(daily["total_value"].iloc[-1]), 0)
        self.assertEqual(set(holdings.columns), {"date", "000001", "000002"})

    def test_dividend_cash_and_reinvest_both_reinvest_on_rebalance_day(self) -> None:
        trading_days = [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
        ]
        stock_pool = [("000001", "Alpha")]
        common_kwargs = {
            "stock_pool": stock_pool,
            "initial_capital": 100_000,
            "target_weight": 1.0,
            "weight_tolerance": 0.0,
            "rebalance_schedule": ["01-03"],
        }
        dividends = {
            "000001": pd.DataFrame(
                {
                    "date": [date(2024, 1, 3)],
                    "cash_dividend": [1.0],
                    "bonus_ratio": [0.0],
                    "transfer_ratio": [0.0],
                }
            )
        }
        quotes = build_quotes({"000001": [10.0, 10.0, 10.0]}, trading_days)
        benchmark = build_benchmark(trading_days)

        reinvest_outputs = run_backtest(
            build_config(dividend_mode="reinvest", **common_kwargs),
            quotes,
            dividends,
            set(trading_days),
            benchmark,
        )
        cash_outputs = run_backtest(
            build_config(dividend_mode="cash", **common_kwargs),
            quotes,
            dividends,
            set(trading_days),
            benchmark,
        )

        reinvest_holdings = reinvest_outputs[2]
        cash_holdings = cash_outputs[2]
        reinvest_trades = reinvest_outputs[1]
        cash_trades = cash_outputs[1]

        self.assertEqual(int(reinvest_holdings["000001"].iloc[-1]), 11000)
        self.assertEqual(int(cash_holdings["000001"].iloc[-1]), 11000)
        self.assertEqual(len(reinvest_trades), 2)
        self.assertEqual(len(cash_trades), 2)

    def test_cash_dividend_is_reinvested_on_next_rebalance_day(self) -> None:
        trading_days = [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
        ]
        config = build_config(
            stock_pool=[("000001", "Alpha")],
            initial_capital=100_000,
            target_weight=1.0,
            weight_tolerance=0.0,
            rebalance_schedule=["01-04"],
            dividend_mode="cash",
        )
        dividends = {
            "000001": pd.DataFrame(
                {
                    "date": [date(2024, 1, 3)],
                    "cash_dividend": [1.0],
                    "bonus_ratio": [0.0],
                    "transfer_ratio": [0.0],
                }
            )
        }
        _, trades, holdings, rebalance_weights = run_backtest(
            config,
            build_quotes({"000001": [10.0, 10.0, 10.0]}, trading_days),
            dividends,
            set(trading_days),
            build_benchmark(trading_days),
        )

        self.assertEqual(len(trades), 2)
        self.assertEqual([trade.reason for trade in trades], ["建仓", "调仓-低配买入"])
        self.assertEqual(int(holdings["000001"].iloc[-1]), 11000)
        self.assertEqual(float(rebalance_weights["cash"].iloc[-1]), 0.0)

    def test_transaction_costs_are_recorded_for_buy_and_sell(self) -> None:
        trading_days = [
            date(2024, 1, 2),
            date(2024, 1, 3),
        ]
        config = build_config(
            stock_pool=[("000001", "Alpha"), ("000002", "Beta")],
            end_date="2024-01-03",
            initial_capital=101_000,
            target_weight=0.5,
            weight_tolerance=0.0,
            rebalance_schedule=["01-03"],
            commission_rate=0.001,
            stamp_tax_rate=0.001,
        )
        daily, trades, holdings, rebalance_weights = run_backtest(
            config,
            build_quotes(
                {
                    "000001": [10.0, 20.0],
                    "000002": [10.0, 10.0],
                },
                trading_days,
            ),
            build_empty_dividends(config.stock_codes),
            set(trading_days),
            build_benchmark(trading_days),
        )

        self.assertEqual(len(trades), 4)
        self.assertEqual([trade.action for trade in trades], ["BUY", "BUY", "SELL", "BUY"])
        self.assertAlmostEqual(sum(trade.commission for trade in trades), 148.0)
        self.assertAlmostEqual(sum(trade.stamp_tax for trade in trades), 24.0)
        self.assertAlmostEqual(sum(trade.transfer_fee for trade in trades), 0.0)
        self.assertEqual(int(holdings["000001"].iloc[-1]), 3800)
        self.assertEqual(int(holdings["000002"].iloc[-1]), 7400)
        self.assertFalse(daily.empty)
        self.assertFalse(rebalance_weights.empty)

    def test_rebalance_count_excludes_initial_buys(self) -> None:
        trading_days = [
            date(2024, 1, 2),
            date(2024, 1, 3),
        ]
        config = build_config(
            stock_pool=[("000001", "Alpha"), ("000002", "Beta")],
            end_date="2024-01-03",
            initial_capital=101_000,
            target_weight=0.5,
            weight_tolerance=0.0,
            rebalance_schedule=["01-03"],
            commission_rate=0.001,
            stamp_tax_rate=0.001,
        )
        daily, trades, _, _ = run_backtest(
            config,
            build_quotes(
                {
                    "000001": [10.0, 20.0],
                    "000002": [10.0, 10.0],
                },
                trading_days,
            ),
            build_empty_dividends(config.stock_codes),
            set(trading_days),
            build_benchmark(trading_days),
        )

        metrics = compute_metrics(config, daily, trades)
        self.assertEqual(metrics["总交易笔数"], 4)
        self.assertEqual(metrics["调仓次数"], 1)

    def test_initial_equal_weight_buys_reserve_room_for_fees(self) -> None:
        trading_days = [
            date(2024, 1, 2),
            date(2024, 1, 3),
        ]
        config = build_config(
            stock_pool=[("000001", "Alpha"), ("000002", "Beta")],
            end_date="2024-01-03",
            initial_capital=100_000,
            target_weight=0.5,
            weight_tolerance=0.0,
            rebalance_schedule=["01-03"],
            commission_rate=0.001,
        )
        _, trades, holdings, _ = run_backtest(
            config,
            build_quotes(
                {
                    "000001": [10.0, 10.0],
                    "000002": [10.0, 10.0],
                },
                trading_days,
            ),
            build_empty_dividends(config.stock_codes),
            set(trading_days),
            build_benchmark(trading_days),
        )

        self.assertEqual([trade.action for trade in trades], ["BUY", "BUY"])
        self.assertEqual(int(holdings["000001"].iloc[0]), 4900)
        self.assertEqual(int(holdings["000002"].iloc[0]), 4900)

    def test_cost_profit_frame_accounts_for_bonus_shares(self) -> None:
        trading_days = [
            date(2024, 1, 2),
            date(2024, 1, 3),
        ]
        config = build_config(
            stock_pool=[("000001", "Alpha")],
            end_date="2024-01-03",
            initial_capital=100_000,
            target_weight=1.0,
            weight_tolerance=0.0,
            rebalance_schedule=["01-03"],
        )
        quotes = build_quotes({"000001": [10.0, 10.0]}, trading_days)
        dividends = {
            "000001": pd.DataFrame(
                {
                    "date": [date(2024, 1, 3)],
                    "cash_dividend": [0.0],
                    "bonus_ratio": [0.1],
                    "transfer_ratio": [0.0],
                }
            )
        }
        _, trades, holdings, _ = run_backtest(
            config,
            quotes,
            dividends,
            set(trading_days),
            build_benchmark(trading_days),
        )

        cost_df = _build_cost_profit_frame(quotes["000001"], trades, dividends["000001"])
        self.assertEqual(int(holdings["000001"].iloc[-1]), 11000)
        self.assertEqual(int(cost_df["shares"].iloc[-1]), 11000)
        self.assertAlmostEqual(float(cost_df["avg_cost"].iloc[-1]), 100000 / 11000, places=6)


if __name__ == "__main__":
    unittest.main()
