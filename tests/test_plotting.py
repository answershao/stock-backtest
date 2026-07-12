import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.plotting import plot_portfolio_history, plot_rebalance_actions, plot_stock_lifecycle_reports


class PlottingTest(unittest.TestCase):
    def test_plot_portfolio_history_writes_file(self) -> None:
        frame = pd.DataFrame(
            [
                {"date": "2024-01-02", "cash": 100.0, "holdings_value": 900.0, "equity": 1000.0},
                {"date": "2024-05-02", "cash": 150.0, "holdings_value": 900.0, "equity": 1050.0},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "portfolio_history.png"
            plot_portfolio_history(
                frame,
                rebalance_dates=(pd.Timestamp("2024-05-02"),),
                output=output,
            )

            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)

    def test_plot_rebalance_actions_writes_file(self) -> None:
        frame = pd.DataFrame(
            [
                {"date": "2024-05-02", "code": "AAA", "action": "BUY"},
                {"date": "2024-05-02", "code": "BBB", "action": "SELL"},
                {"date": "2024-11-01", "code": "CCC", "action": "HOLD"},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rebalance_actions.png"
            plot_rebalance_actions(frame, output=output)

            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)

    def test_plot_stock_lifecycle_reports_writes_files(self) -> None:
        price_df = pd.DataFrame(
            [
                {"date": "2024-01-02", "code": "AAA", "close": 10.0},
                {"date": "2024-01-03", "code": "AAA", "close": 11.0},
                {"date": "2024-01-04", "code": "AAA", "close": 12.0},
            ]
        )
        trade_log = pd.DataFrame(
            [
                {"date": "2024-01-02", "code": "AAA", "action": "BUY", "shares": 10.0, "price": 10.0, "trade_value": 100.0, "signed_trade_value": 100.0},
                {"date": "2024-01-04", "code": "AAA", "action": "SELL", "shares": 10.0, "price": 12.0, "trade_value": 120.0, "signed_trade_value": -120.0},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "stock_reports"
            plot_stock_lifecycle_reports(
                price_df,
                trade_log,
                output_dir=output_dir,
                stock_name_map={"AAA": "测试股票"},
                stock_pool=["AAA"],
            )

            self.assertTrue((output_dir / "stock_report_summary.csv").exists())
            self.assertTrue((output_dir / "AAA.png").exists())
            self.assertGreater((output_dir / "AAA.png").stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
