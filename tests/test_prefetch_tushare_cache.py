import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.data.tushare_strategy import FULL_HISTORY_START_DATE, prefetch_tushare_strategy_cache


class PrefetchTushareCacheTest(unittest.TestCase):
    def test_report_rc_fetch_paginates_until_empty(self) -> None:
        from backtest.data.tushare_expected_return import fetch_report_rc_from_tushare

        class FakePro:
            def __init__(self) -> None:
                self.calls = []

            def report_rc(self, **kwargs) -> pd.DataFrame:
                self.calls.append(kwargs)
                offset = kwargs.get("offset", 0)
                limit = kwargs.get("limit", 3000)
                rows = []
                for idx in range(offset, min(offset + limit, 6500)):
                    rows.append(
                        {
                            "org_name": f"org_{idx}",
                            "quarter": "2026Q4",
                            "report_date": f"2024{(idx % 12) + 1:02d}01",
                            "eps": float(idx),
                        }
                    )
                return pd.DataFrame(rows)

        pro = FakePro()
        frame = fetch_report_rc_from_tushare(pro, "600519.SH", "20100101", "20241231")

        self.assertEqual(len(frame), 6500)
        self.assertEqual([call["offset"] for call in pro.calls], [0, 3000, 6000])

    def test_prefetch_writes_required_cache_sets(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.trade_cal_args = []
                self.daily_args = []
                self.dividend_args = []

            def trade_cal(self, **kwargs) -> pd.DataFrame:
                self.trade_cal_args.append(kwargs)
                return pd.DataFrame(
                    [
                        {"cal_date": "20240102", "is_open": 1},
                        {"cal_date": "20240502", "is_open": 1},
                        {"cal_date": "20241101", "is_open": 1},
                    ]
                )

            def daily(self, **kwargs) -> pd.DataFrame:
                self.daily_args.append(kwargs)
                return pd.DataFrame(
                    [
                        {"ts_code": "600519.SH", "trade_date": "20241101", "close": 10.0},
                        {"ts_code": "600519.SH", "trade_date": "20240502", "close": 10.0},
                        {"ts_code": "600519.SH", "trade_date": "20240102", "close": 10.0},
                    ]
                )

            def daily_basic(self, **kwargs) -> pd.DataFrame:
                rows = []
                for idx in range(12):
                    rows.append(
                        {
                            "ts_code": "600519.SH",
                            "trade_date": f"2023{idx + 1:02d}01",
                            "pe_ttm": float(10 + idx),
                        }
                    )
                rows.append({"ts_code": "600519.SH", "trade_date": "20240102", "pe_ttm": 20.0})
                rows.append({"ts_code": "600519.SH", "trade_date": "20240502", "pe_ttm": 21.0})
                rows.append({"ts_code": "600519.SH", "trade_date": "20241101", "pe_ttm": 22.0})
                return pd.DataFrame(rows)

            def report_rc(self, **kwargs) -> pd.DataFrame:
                offset = kwargs.get("offset", 0)
                limit = kwargs.get("limit", 3000)
                if offset > 0:
                    return pd.DataFrame()
                return pd.DataFrame(
                    [
                        {"org_name": "A", "quarter": "2026Q4", "report_date": "20240101", "eps": 15.0},
                    ][:limit]
                )

            def fina_indicator(self, **kwargs) -> pd.DataFrame:
                return pd.DataFrame(
                    [
                        {"ann_date": "20240320", "end_date": "20231231", "eps": 10.0},
                    ]
                )

            def dividend(self, **kwargs) -> pd.DataFrame:
                self.dividend_args.append(kwargs)
                return pd.DataFrame(
                    [
                        {"ts_code": "600519.SH", "ex_date": "20240502", "cash_div": 1.5, "div_proc": "实施"},
                    ]
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            pro = FakePro()
            artifacts = prefetch_tushare_strategy_cache(
                pro,
                stock_pool=["600519.SH"],
                end_date="20241231",
                cache_dir=cache_dir,
            )

            self.assertEqual(len(artifacts.trading_dates), 3)
            self.assertEqual(pro.trade_cal_args[0]["start_date"], FULL_HISTORY_START_DATE)
            self.assertEqual(pro.daily_args[0]["start_date"], FULL_HISTORY_START_DATE)
            self.assertTrue((cache_dir / "trade_cal").exists())
            self.assertTrue((cache_dir / "daily").exists())
            self.assertTrue((cache_dir / "daily_basic").exists())
            self.assertTrue((cache_dir / "report_rc").exists())
            self.assertTrue((cache_dir / "fina_indicator").exists())
            self.assertTrue((cache_dir / "dividend").exists())

    def test_prefetch_updates_cache_incrementally_without_clearing(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.trade_cal_args = []
                self.daily_args = []
                self.daily_basic_args = []
                self.dividend_args = []
                self.dividend_args = []
                self.dividend_args = []
                self.dividend_args = []
                self.dividend_args = []
                self.dividend_args = []
                self.dividend_args = []
                self.report_rc_args = []
                self.fina_indicator_args = []
                self.dividend_args = []

            def trade_cal(self, **kwargs) -> pd.DataFrame:
                self.trade_cal_args.append(kwargs)
                start_date = kwargs["start_date"]
                end_date = kwargs["end_date"]
                rows = []
                if start_date <= "20240102" <= end_date:
                    rows.append({"cal_date": "20240102", "is_open": 1})
                if start_date <= "20240103" <= end_date:
                    rows.append({"cal_date": "20240103", "is_open": 1})
                return pd.DataFrame(rows)

            def daily(self, **kwargs) -> pd.DataFrame:
                self.daily_args.append(kwargs)
                start_date = kwargs["start_date"]
                end_date = kwargs["end_date"]
                rows = []
                if start_date <= "20240102" <= end_date:
                    rows.append({"ts_code": "600519.SH", "trade_date": "20240102", "close": 10.0})
                if start_date <= "20240103" <= end_date:
                    rows.append({"ts_code": "600519.SH", "trade_date": "20240103", "close": 11.0})
                return pd.DataFrame(rows)

            def daily_basic(self, **kwargs) -> pd.DataFrame:
                self.daily_basic_args.append(kwargs)
                start_date = kwargs["start_date"]
                end_date = kwargs["end_date"]
                rows = []
                if start_date <= "20240102" <= end_date:
                    rows.append({"ts_code": "600519.SH", "trade_date": "20240102", "pe_ttm": 20.0})
                if start_date <= "20240103" <= end_date:
                    rows.append({"ts_code": "600519.SH", "trade_date": "20240103", "pe_ttm": 21.0})
                return pd.DataFrame(rows)

            def report_rc(self, **kwargs) -> pd.DataFrame:
                self.report_rc_args.append(kwargs)
                start_date = kwargs["start_date"]
                end_date = kwargs["end_date"]
                offset = kwargs.get("offset", 0)
                if offset > 0:
                    return pd.DataFrame()
                rows = []
                if start_date <= "20240102" <= end_date:
                    rows.append({"org_name": "A", "quarter": "2026Q4", "report_date": "20240102", "eps": 15.0})
                if start_date <= "20240103" <= end_date:
                    rows.append({"org_name": "B", "quarter": "2026Q4", "report_date": "20240103", "eps": 16.0})
                return pd.DataFrame(rows)

            def fina_indicator(self, **kwargs) -> pd.DataFrame:
                self.fina_indicator_args.append(kwargs)
                start_date = kwargs["start_date"]
                end_date = kwargs["end_date"]
                rows = []
                if start_date <= "20240102" <= end_date:
                    rows.append({"ann_date": "20240102", "end_date": "20231231", "eps": 10.0})
                if start_date <= "20240103" <= end_date:
                    rows.append({"ann_date": "20240103", "end_date": "20231231", "eps": 10.5})
                return pd.DataFrame(rows)

            def dividend(self, **kwargs) -> pd.DataFrame:
                self.dividend_args.append(kwargs)
                start_date = kwargs["start_date"]
                end_date = kwargs["end_date"]
                rows = []
                if start_date <= "20240102" <= end_date:
                    rows.append({"ts_code": "600519.SH", "ex_date": "20240102", "cash_div": 1.0, "div_proc": "实施"})
                if start_date <= "20240103" <= end_date:
                    rows.append({"ts_code": "600519.SH", "ex_date": "20240103", "cash_div": 1.2, "div_proc": "实施"})
                return pd.DataFrame(rows)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            marker = cache_dir / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            pro = FakePro()

            prefetch_tushare_strategy_cache(
                pro,
                stock_pool=["600519.SH"],
                end_date="20240102",
                cache_dir=cache_dir,
            )
            prefetch_tushare_strategy_cache(
                pro,
                stock_pool=["600519.SH"],
                end_date="20240103",
                cache_dir=cache_dir,
            )
            prefetch_tushare_strategy_cache(
                pro,
                stock_pool=["600519.SH"],
                end_date="20240103",
                cache_dir=cache_dir,
                refresh_datasets=("report_rc",),
            )

            self.assertTrue(marker.exists())
            self.assertEqual(
                [args["start_date"] for args in pro.trade_cal_args],
                [FULL_HISTORY_START_DATE, "20240103"],
            )
            self.assertEqual(
                [args["start_date"] for args in pro.daily_args],
                [FULL_HISTORY_START_DATE, "20240103"],
            )
            self.assertEqual(
                [args["start_date"] for args in pro.daily_basic_args],
                [FULL_HISTORY_START_DATE, "20240103"],
            )
            self.assertEqual(
                [args["start_date"] for args in pro.fina_indicator_args],
                [FULL_HISTORY_START_DATE, "20240103"],
            )
            self.assertEqual(
                [args["start_date"] for args in pro.dividend_args],
                [FULL_HISTORY_START_DATE, "20240103"],
            )
            self.assertEqual(
                [args["start_date"] for args in pro.report_rc_args if args.get("offset", 0) == 0],
                [FULL_HISTORY_START_DATE, "20240103", FULL_HISTORY_START_DATE],
            )

            trade_cal_files = sorted((cache_dir / "trade_cal").glob("*.csv"))
            self.assertEqual([file.name for file in trade_cal_files], ["full__is_open_1.csv"])
            report_rc_files = sorted((cache_dir / "report_rc").glob("*.csv"))
            self.assertEqual([file.name for file in report_rc_files], ["600519.SH.csv"])

    def test_prefetch_resolves_non_trading_end_date_for_trade_datasets(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.trade_cal_args = []
                self.daily_args = []
                self.daily_basic_args = []
                self.dividend_args = []

            def trade_cal(self, **kwargs) -> pd.DataFrame:
                self.trade_cal_args.append(kwargs)
                return pd.DataFrame(
                    [
                        {"cal_date": "20240104", "is_open": 1},
                        {"cal_date": "20240105", "is_open": 1},
                    ]
                )

            def daily(self, **kwargs) -> pd.DataFrame:
                self.daily_args.append(kwargs)
                return pd.DataFrame(
                    [
                        {"ts_code": "600519.SH", "trade_date": "20240105", "close": 11.0},
                    ]
                )

            def daily_basic(self, **kwargs) -> pd.DataFrame:
                self.daily_basic_args.append(kwargs)
                return pd.DataFrame(
                    [
                        {"ts_code": "600519.SH", "trade_date": "20240105", "pe_ttm": 21.0},
                    ]
                )

            def report_rc(self, **kwargs) -> pd.DataFrame:
                return pd.DataFrame()

            def fina_indicator(self, **kwargs) -> pd.DataFrame:
                return pd.DataFrame()

            def dividend(self, **kwargs) -> pd.DataFrame:
                self.dividend_args.append(kwargs)
                return pd.DataFrame()

        with tempfile.TemporaryDirectory() as tmpdir:
            pro = FakePro()
            prefetch_tushare_strategy_cache(
                pro,
                stock_pool=["600519.SH"],
                end_date="20240106",
                cache_dir=Path(tmpdir),
            )

        self.assertEqual(pro.daily_args[0]["end_date"], "20240105")
        self.assertEqual(pro.daily_basic_args[0]["end_date"], "20240105")
        self.assertEqual(pro.dividend_args[0]["end_date"], "20240106")


if __name__ == "__main__":
    unittest.main()
