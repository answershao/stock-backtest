import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.stock_pool import parse_stock_pool
from backtest.data.tushare_strategy import (
    calculate_expected_return_from_cache,
    resolve_strategy_dates,
    run_tushare_expected_return_backtest,
)


class TushareStrategyHelpersTest(unittest.TestCase):
    def test_parse_stock_pool(self) -> None:
        self.assertEqual(
            parse_stock_pool("600519.SH, 000858.SZ , ,600036.SH"),
            ["600519.SH", "000858.SZ", "600036.SH"],
        )

    def test_resolve_strategy_dates_rolls_forward_to_next_trade_day(self) -> None:
        trading_dates = (
            pd.Timestamp("2024-01-02"),
            pd.Timestamp("2024-05-02"),
            pd.Timestamp("2024-11-01"),
        )
        actual_start, rebalance_dates = resolve_strategy_dates(
            trading_dates=trading_dates,
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        self.assertEqual(actual_start, pd.Timestamp("2024-01-02"))
        self.assertEqual(
            rebalance_dates,
            (pd.Timestamp("2024-05-02"), pd.Timestamp("2024-11-01")),
        )

    def test_calculates_expected_return_from_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            (cache_dir / "trade_cal").mkdir()
            (cache_dir / "daily_basic").mkdir()
            (cache_dir / "report_rc").mkdir()
            (cache_dir / "fina_indicator").mkdir()

            pd.DataFrame(
                [{"cal_date": "20240102", "is_open": 1}, {"cal_date": "20240502", "is_open": 1}]
            ).to_csv(cache_dir / "trade_cal" / "19900101__20241231__is_open_1.csv", index=False)

            pd.DataFrame(
                [
                    {"ts_code": "600519.SH", "trade_date": "20230101", "pe_ttm": 10.0},
                    {"ts_code": "600519.SH", "trade_date": "20230201", "pe_ttm": 11.0},
                    {"ts_code": "600519.SH", "trade_date": "20230301", "pe_ttm": 12.0},
                    {"ts_code": "600519.SH", "trade_date": "20230401", "pe_ttm": 13.0},
                    {"ts_code": "600519.SH", "trade_date": "20230501", "pe_ttm": 14.0},
                    {"ts_code": "600519.SH", "trade_date": "20230601", "pe_ttm": 15.0},
                    {"ts_code": "600519.SH", "trade_date": "20230701", "pe_ttm": 16.0},
                    {"ts_code": "600519.SH", "trade_date": "20230801", "pe_ttm": 17.0},
                    {"ts_code": "600519.SH", "trade_date": "20230901", "pe_ttm": 18.0},
                    {"ts_code": "600519.SH", "trade_date": "20231001", "pe_ttm": 19.0},
                    {"ts_code": "600519.SH", "trade_date": "20231101", "pe_ttm": 20.0},
                    {"ts_code": "600519.SH", "trade_date": "20231201", "pe_ttm": 21.0},
                    {"ts_code": "600519.SH", "trade_date": "20240102", "pe_ttm": 20.0},
                ]
            ).to_csv(cache_dir / "daily_basic" / "600519.SH__19900101__20241231__pe_ttm.csv", index=False)

            pd.DataFrame(
                [{"org_name": "A", "quarter": "2026Q4", "report_date": "20240101", "eps": 15.0}]
            ).to_csv(cache_dir / "report_rc" / "600519.SH__19900101__20241231.csv", index=False)

            pd.DataFrame(
                [{"ann_date": "20240320", "end_date": "20231231", "eps": 10.0}]
            ).to_csv(cache_dir / "fina_indicator" / "600519.SH__19900101__20241231.csv", index=False)

            snapshot = calculate_expected_return_from_cache(
                ts_code="600519.SH",
                as_of_date="20240502",
                cache_dir=cache_dir,
            )

        self.assertEqual(snapshot.ts_code, "600519.SH")
        self.assertEqual(snapshot.as_of_date, "20240502")
        self.assertTrue(snapshot.result.valid)

    def test_backtest_cache_only_raises_when_required_cache_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            with self.assertRaises(FileNotFoundError):
                run_tushare_expected_return_backtest(
                    None,
                    stock_pool=["600519.SH"],
                    start_date="20240101",
                    end_date="20241231",
                    cache_dir=cache_dir,
                    cache_only=True,
                )


if __name__ == "__main__":
    unittest.main()
