import unittest

import pandas as pd

from backtest.strategy import StrategyConfig, run_expected_return_strategy


class ExpectedReturnStrategyBacktestTest(unittest.TestCase):
    def test_builds_positions_rebalances_and_keeps_cash(self) -> None:
        price_df = pd.DataFrame(
            [
                {"date": "2024-01-02", "code": "AAA", "close": 10.0},
                {"date": "2024-01-02", "code": "BBB", "close": 20.0},
                {"date": "2024-01-02", "code": "CCC", "close": 30.0},
                {"date": "2024-01-02", "code": "DDD", "close": 40.0},
                {"date": "2024-05-02", "code": "AAA", "close": 10.0},
                {"date": "2024-05-02", "code": "BBB", "close": 20.0},
                {"date": "2024-05-02", "code": "CCC", "close": 30.0},
                {"date": "2024-05-02", "code": "DDD", "close": 40.0},
                {"date": "2024-11-01", "code": "AAA", "close": 10.0},
                {"date": "2024-11-01", "code": "BBB", "close": 20.0},
                {"date": "2024-11-01", "code": "CCC", "close": 30.0},
                {"date": "2024-11-01", "code": "DDD", "close": 40.0},
            ]
        )
        signal_df = pd.DataFrame(
            [
                {"date": "2024-01-02", "code": "AAA", "expected_return_3y": 0.30},
                {"date": "2024-01-02", "code": "BBB", "expected_return_3y": 0.25},
                {"date": "2024-01-02", "code": "CCC", "expected_return_3y": 0.10},
                {"date": "2024-01-02", "code": "DDD", "expected_return_3y": 0.05},
                {"date": "2024-05-02", "code": "AAA", "expected_return_3y": -0.10},
                {"date": "2024-05-02", "code": "BBB", "expected_return_3y": 0.10},
                {"date": "2024-05-02", "code": "CCC", "expected_return_3y": 0.35},
                {"date": "2024-05-02", "code": "DDD", "expected_return_3y": 0.21},
                {"date": "2024-11-01", "code": "AAA", "expected_return_3y": 0.05},
                {"date": "2024-11-01", "code": "BBB", "expected_return_3y": 0.05},
                {"date": "2024-11-01", "code": "CCC", "expected_return_3y": 0.05},
                {"date": "2024-11-01", "code": "DDD", "expected_return_3y": 0.05},
            ]
        )

        result = run_expected_return_strategy(
            price_df=price_df,
            signal_df=signal_df,
            start_date="2024-01-01",
            end_date="2024-11-01",
            config=StrategyConfig(initial_cash=1000.0),
        )

        self.assertEqual(
            result.rebalance_dates,
            (pd.Timestamp("2024-05-02"), pd.Timestamp("2024-11-01")),
        )

        initial_trades = result.trade_log[result.trade_log["date"] == pd.Timestamp("2024-01-02")]
        self.assertCountEqual(initial_trades["code"].tolist(), ["AAA", "BBB"])

        may_trades = result.trade_log[result.trade_log["date"] == pd.Timestamp("2024-05-02")]
        sell_codes = may_trades[may_trades["action"] == "SELL"]["code"].tolist()
        buy_codes = may_trades[may_trades["action"] == "BUY"]["code"].tolist()
        self.assertIn("AAA", sell_codes)
        self.assertIn("CCC", buy_codes)
        self.assertIn("DDD", buy_codes)

        may_holdings = result.holdings_history[result.holdings_history["date"] == pd.Timestamp("2024-05-02")]
        self.assertCountEqual(may_holdings["code"].tolist(), ["BBB", "CCC", "DDD"])
        for weight in may_holdings["weight"].tolist():
            self.assertAlmostEqual(weight, 0.05)

        final_row = result.portfolio_history.iloc[-1]
        self.assertEqual(final_row["positions"], 3)
        self.assertAlmostEqual(final_row["cash"], 850.0)
        self.assertAlmostEqual(final_row["equity"], 1000.0)

    def test_keeps_existing_holding_when_signal_is_missing(self) -> None:
        price_df = pd.DataFrame(
            [
                {"date": "2024-01-02", "code": "AAA", "close": 10.0},
                {"date": "2024-05-02", "code": "AAA", "close": 10.0},
                {"date": "2024-05-02", "code": "BBB", "close": 20.0},
            ]
        )
        signal_df = pd.DataFrame(
            [
                {"date": "2024-01-02", "code": "AAA", "expected_return_3y": 0.30},
                {"date": "2024-05-02", "code": "BBB", "expected_return_3y": 0.25},
            ]
        )

        result = run_expected_return_strategy(
            price_df=price_df,
            signal_df=signal_df,
            start_date="2024-01-02",
            end_date="2024-05-02",
            config=StrategyConfig(initial_cash=1000.0),
        )

        may_holdings = result.holdings_history[result.holdings_history["date"] == pd.Timestamp("2024-05-02")]
        self.assertIn("AAA", may_holdings["code"].tolist())


if __name__ == "__main__":
    unittest.main()
