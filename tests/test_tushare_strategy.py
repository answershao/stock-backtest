import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.stock_pool import parse_stock_pool
from src.data.tushare_strategy import (
    calculate_expected_return_from_cache,
    resolve_strategy_dates,
    run_tushare_expected_return_backtest,
)
from src.strategy import StrategyConfig


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

    def test_backtest_reinvests_dividend_cash_from_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            for dataset in ("trade_cal", "daily", "daily_basic", "report_rc", "fina_indicator", "dividend"):
                (cache_dir / dataset).mkdir()

            pd.DataFrame(
                [
                    {"cal_date": "20240102", "is_open": 1},
                    {"cal_date": "20240502", "is_open": 1},
                ]
            ).to_csv(cache_dir / "trade_cal" / "full__is_open_1.csv", index=False)

            pd.DataFrame(
                [
                    {"ts_code": "600519.SH", "trade_date": "20240102", "close": 10.0},
                    {"ts_code": "600519.SH", "trade_date": "20240502", "close": 10.0},
                    {"ts_code": "000858.SZ", "trade_date": "20240102", "close": 10.0},
                    {"ts_code": "000858.SZ", "trade_date": "20240502", "close": 10.0},
                ]
            ).to_csv(cache_dir / "daily" / "600519.SH__close.csv", index=False)
            pd.DataFrame(
                [
                    {"ts_code": "000858.SZ", "trade_date": "20240102", "close": 10.0},
                    {"ts_code": "000858.SZ", "trade_date": "20240502", "close": 10.0},
                ]
            ).to_csv(cache_dir / "daily" / "000858.SZ__close.csv", index=False)

            history_rows = []
            for idx in range(12):
                trade_date = f"2023{idx + 1:02d}01"
                history_rows.append({"ts_code": "600519.SH", "trade_date": trade_date, "pe_ttm": float(10 + idx)})
                history_rows.append({"ts_code": "000858.SZ", "trade_date": trade_date, "pe_ttm": float(10 + idx)})
            history_rows.extend(
                [
                    {"ts_code": "600519.SH", "trade_date": "20240102", "pe_ttm": 20.0},
                    {"ts_code": "600519.SH", "trade_date": "20240502", "pe_ttm": 20.0},
                    {"ts_code": "000858.SZ", "trade_date": "20240102", "pe_ttm": 20.0},
                    {"ts_code": "000858.SZ", "trade_date": "20240502", "pe_ttm": 20.0},
                ]
            )
            pd.DataFrame([row for row in history_rows if row["ts_code"] == "600519.SH"]).to_csv(
                cache_dir / "daily_basic" / "600519.SH__pe_ttm.csv",
                index=False,
            )
            pd.DataFrame([row for row in history_rows if row["ts_code"] == "000858.SZ"]).to_csv(
                cache_dir / "daily_basic" / "000858.SZ__pe_ttm.csv",
                index=False,
            )

            pd.DataFrame(
                [{"org_name": "A", "quarter": "2025Q4", "report_date": "20240101", "eps": 20.0}]
            ).to_csv(cache_dir / "report_rc" / "600519.SH.csv", index=False)
            pd.DataFrame(
                [{"org_name": "A", "quarter": "2025Q4", "report_date": "20240101", "eps": 20.0}]
            ).to_csv(cache_dir / "report_rc" / "000858.SZ.csv", index=False)

            pd.DataFrame(
                [{"ann_date": "20231231", "end_date": "20221231", "eps": 10.0}]
            ).to_csv(cache_dir / "fina_indicator" / "600519.SH.csv", index=False)
            pd.DataFrame(
                [{"ann_date": "20231231", "end_date": "20221231", "eps": 10.0}]
            ).to_csv(cache_dir / "fina_indicator" / "000858.SZ.csv", index=False)

            pd.DataFrame(
                [{"ts_code": "600519.SH", "ex_date": "20240502", "cash_div": 1.0, "div_proc": "实施"}]
            ).to_csv(cache_dir / "dividend" / "600519.SH.csv", index=False)
            pd.DataFrame(
                [{"ts_code": "000858.SZ", "ex_date": "20230101", "cash_div": 0.0, "div_proc": "实施"}]
            ).to_csv(
                cache_dir / "dividend" / "000858.SZ.csv",
                index=False,
            )

            artifacts = run_tushare_expected_return_backtest(
                None,
                stock_pool=["600519.SH", "000858.SZ"],
                start_date="20240101",
                end_date="20240502",
                strategy_config=StrategyConfig(
                    initial_cash=1_000_000.0,
                    max_positions=2,
                    target_weight=0.5,
                    entry_threshold=-1.0,
                    exit_threshold=-1.0,
                    rebalance_month_days=("05-01",),
                ),
                cache_dir=cache_dir,
                cache_only=True,
            )

        final_row = artifacts.backtest_result.portfolio_history.iloc[-1]

        self.assertAlmostEqual(final_row["equity"], 1050000.0)
        self.assertAlmostEqual(final_row["dividend_cash"], 50000.0)
        self.assertAlmostEqual(final_row["cash"], 0.0)


if __name__ == "__main__":
    unittest.main()
