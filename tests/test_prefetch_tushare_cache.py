import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data.tushare_cache_prefetch import FULL_HISTORY_START_DATE, prefetch_tushare_cache


class PrefetchTushareCacheTest(unittest.TestCase):
    def test_report_rc_fetch_paginates_until_empty(self) -> None:
        from src.data.tushare_expected_return import fetch_report_rc_from_tushare

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
        self.assertIn("quarter", frame.columns)
        self.assertIn("eps", frame.columns)

    def test_prefetch_writes_required_cache_sets(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.trade_cal_args = []
                self.daily_basic_args = []
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

            def daily_basic(self, **kwargs) -> pd.DataFrame:
                self.daily_basic_args.append(kwargs)
                rows = []
                for idx in range(12):
                    rows.append(
                        {
                            "ts_code": "600519.SH",
                            "trade_date": f"2023{idx + 1:02d}01",
                            "pe_ttm": float(10 + idx),
                            "close": float(10 + idx),
                        }
                    )
                rows.append({"ts_code": "600519.SH", "trade_date": "20240102", "pe_ttm": 20.0, "close": 10.0})
                rows.append({"ts_code": "600519.SH", "trade_date": "20240502", "pe_ttm": 21.0, "close": 10.0})
                rows.append({"ts_code": "600519.SH", "trade_date": "20241101", "pe_ttm": 22.0, "close": 10.0})
                return pd.DataFrame(rows)

            def report_rc(self, **kwargs) -> pd.DataFrame:
                offset = kwargs.get("offset", 0)
                limit = kwargs.get("limit", 3000)
                if offset > 0:
                    return pd.DataFrame()
                return pd.DataFrame(
                    [
                        {"org_name": "A", "quarter": "2026Q4", "report_date": "20240101", "eps": 15.0},
                        {"org_name": "A", "quarter": "2027Q4", "report_date": "20240101", "eps": 18.0},
                    ][:limit]
                )

            def fina_indicator(self, **kwargs) -> pd.DataFrame:
                return pd.DataFrame(
                    [
                        {"ann_date": "20230820", "end_date": "20230630", "eps": 8.0},
                        {"ann_date": "20240320", "end_date": "20231231", "eps": 10.0},
                    ]
                )

            def dividend(self, **kwargs) -> pd.DataFrame:
                self.dividend_args.append(kwargs)
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "600519.SH",
                            "ann_date": "20240418",
                            "record_date": "20240430",
                            "ex_date": "20240501",
                            "imp_ann_date": "20240419",
                            "cash_div": 1.2,
                            "stk_div": 0.6,
                            "stk_bo_rate": 0.1,
                            "stk_co_rate": 0.5,
                            "div_proc": "预案",
                        },
                        {
                            "ts_code": "600519.SH",
                            "ann_date": "20240420",
                            "record_date": "20240501",
                            "ex_date": "20240502",
                            "imp_ann_date": "20240421",
                            "cash_div": 1.5,
                            "stk_div": 1.0,
                            "stk_bo_rate": 0.2,
                            "stk_co_rate": 0.8,
                            "div_proc": "实施",
                        },
                    ]
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            pro = FakePro()
            artifacts = prefetch_tushare_cache(
                pro,
                stock_pool=["600519.SH"],
                end_date="20241231",
                cache_dir=cache_dir,
            )

            self.assertEqual(len(artifacts.trading_dates), 3)
            self.assertEqual(pro.trade_cal_args[0]["start_date"], FULL_HISTORY_START_DATE)
            self.assertEqual(pro.daily_basic_args[0]["start_date"], FULL_HISTORY_START_DATE)
            self.assertTrue((cache_dir / "trade_cal").exists())
            self.assertTrue((cache_dir / "daily_basic").exists())
            self.assertTrue((cache_dir / "report_rc").exists())
            self.assertTrue((cache_dir / "fina_indicator").exists())
            self.assertTrue((cache_dir / "dividend").exists())
            report_rc = pd.read_csv(cache_dir / "report_rc" / "600519.SH.csv")
            self.assertEqual(report_rc.columns.tolist(), ["org_name", "quarter", "report_date", "eps"])
            self.assertEqual(report_rc["quarter"].tolist(), ["2026Q4", "2027Q4"])
            self.assertEqual(report_rc["eps"].tolist(), [15.0, 18.0])
            fina_indicator = pd.read_csv(cache_dir / "fina_indicator" / "600519.SH.csv")
            self.assertEqual(fina_indicator["end_date"].astype(str).tolist(), ["20231231"])
            dividend = pd.read_csv(cache_dir / "dividend" / "600519.SH.csv")
            self.assertEqual(
                dividend.loc[0, ["stk_div", "stk_bo_rate", "stk_co_rate"]].tolist(),
                [1.0, 0.2, 0.8],
            )
            self.assertEqual(dividend["div_proc"].astype(str).tolist(), ["实施"])

    def test_prefetch_updates_cache_incrementally_without_clearing(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.trade_cal_args = []
                self.daily_basic_args = []
                self.dividend_args = []
                self.report_rc_args = []
                self.fina_indicator_args = []

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

            def daily_basic(self, **kwargs) -> pd.DataFrame:
                self.daily_basic_args.append(kwargs)
                start_date = kwargs["start_date"]
                end_date = kwargs["end_date"]
                rows = []
                if start_date <= "20240102" <= end_date:
                    rows.append({"ts_code": "600519.SH", "trade_date": "20240102", "pe_ttm": 20.0, "close": 10.0})
                if start_date <= "20240103" <= end_date:
                    rows.append({"ts_code": "600519.SH", "trade_date": "20240103", "pe_ttm": 21.0, "close": 11.0})
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
                    rows.append({"org_name": "A", "quarter": "2027Q4", "report_date": "20240102", "eps": 18.0})
                if start_date <= "20240103" <= end_date:
                    rows.append({"org_name": "B", "quarter": "2026Q4", "report_date": "20240103", "eps": 16.0})
                    rows.append({"org_name": "B", "quarter": "2027Q4", "report_date": "20240103", "eps": 19.0})
                return pd.DataFrame(rows)

            def fina_indicator(self, **kwargs) -> pd.DataFrame:
                self.fina_indicator_args.append(kwargs)
                start_date = kwargs["start_date"]
                end_date = kwargs["end_date"]
                rows = []
                if start_date <= "20240102" <= end_date:
                    rows.append({"ann_date": "20240102", "end_date": "20230930", "eps": 9.0})
                    rows.append({"ann_date": "20240102", "end_date": "20231231", "eps": 10.0})
                if start_date <= "20240103" <= end_date:
                    rows.append({"ann_date": "20240103", "end_date": "20231231", "eps": 10.5})
                return pd.DataFrame(rows)

            def dividend(self, **kwargs) -> pd.DataFrame:
                self.dividend_args.append(kwargs)
                rows = []
                rows.append({"ts_code": "600519.SH", "ann_date": "20231231", "record_date": "20231231", "ex_date": "20240101", "imp_ann_date": "20231231", "cash_div": 0.8, "stk_div": 0.4, "stk_bo_rate": 0.1, "stk_co_rate": 0.3, "div_proc": "预案"})
                rows.append({"ts_code": "600519.SH", "ann_date": "20240101", "record_date": "20240101", "ex_date": "20240102", "imp_ann_date": "20240101", "cash_div": 1.0, "stk_div": 0.5, "stk_bo_rate": 0.2, "stk_co_rate": 0.3, "div_proc": "实施"})
                rows.append({"ts_code": "600519.SH", "ann_date": "20240102", "record_date": "20240102", "ex_date": "20240103", "imp_ann_date": "20240102", "cash_div": 1.2, "stk_div": 0.6, "stk_bo_rate": 0.1, "stk_co_rate": 0.5, "div_proc": "实施"})
                return pd.DataFrame(rows)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            marker = cache_dir / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            pro = FakePro()

            prefetch_tushare_cache(
                pro,
                stock_pool=["600519.SH"],
                end_date="20240102",
                cache_dir=cache_dir,
            )
            prefetch_tushare_cache(
                pro,
                stock_pool=["600519.SH"],
                end_date="20240103",
                cache_dir=cache_dir,
            )
            prefetch_tushare_cache(
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
                [args["start_date"] for args in pro.daily_basic_args],
                [FULL_HISTORY_START_DATE, "20240103"],
            )
            self.assertEqual(
                [args["start_date"] for args in pro.fina_indicator_args],
                [FULL_HISTORY_START_DATE, "20240103"],
            )
            self.assertEqual(
                [args["ts_code"] for args in pro.dividend_args],
                ["600519.SH", "600519.SH", "600519.SH"],
            )
            self.assertEqual(
                [args["start_date"] for args in pro.report_rc_args if args.get("offset", 0) == 0],
                [FULL_HISTORY_START_DATE, "20240103", FULL_HISTORY_START_DATE],
            )

            trade_cal_files = sorted((cache_dir / "trade_cal").glob("*.csv"))
            self.assertEqual([file.name for file in trade_cal_files], ["full__is_open_1.csv"])
            report_rc_files = sorted((cache_dir / "report_rc").glob("*.csv"))
            self.assertEqual([file.name for file in report_rc_files], ["600519.SH.csv"])
            report_rc = pd.read_csv(cache_dir / "report_rc" / "600519.SH.csv")
            self.assertEqual(report_rc["report_date"].astype(str).tolist(), ["20240102", "20240102", "20240103", "20240103"])
            self.assertEqual(report_rc["org_name"].tolist(), ["A", "A", "B", "B"])
            self.assertEqual(report_rc["quarter"].tolist(), ["2026Q4", "2027Q4", "2026Q4", "2027Q4"])
            self.assertEqual(report_rc["eps"].tolist(), [15.0, 18.0, 16.0, 19.0])
            fina_indicator = pd.read_csv(cache_dir / "fina_indicator" / "600519.SH.csv")
            self.assertEqual(fina_indicator["end_date"].astype(str).tolist(), ["20231231"])
            self.assertEqual(fina_indicator["ann_date"].astype(str).tolist(), ["20240103"])
            self.assertEqual(fina_indicator["eps"].tolist(), [10.5])
            dividend = pd.read_csv(cache_dir / "dividend" / "600519.SH.csv")
            self.assertEqual(dividend["div_proc"].astype(str).tolist(), ["实施", "实施"])

    def test_prefetch_resolves_non_trading_end_date_for_trade_datasets(self) -> None:
        class FakePro:
            def __init__(self) -> None:
                self.trade_cal_args = []
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

            def daily_basic(self, **kwargs) -> pd.DataFrame:
                self.daily_basic_args.append(kwargs)
                return pd.DataFrame(
                    [
                        {"ts_code": "600519.SH", "trade_date": "20240105", "pe_ttm": 21.0, "close": 11.0},
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
            prefetch_tushare_cache(
                pro,
                stock_pool=["600519.SH"],
                end_date="20240106",
                cache_dir=Path(tmpdir),
            )

        self.assertEqual(pro.daily_basic_args[0]["end_date"], "20240105")
        self.assertEqual(pro.dividend_args[0]["ts_code"], "600519.SH")
        self.assertIn("fields", pro.dividend_args[0])


if __name__ == "__main__":
    unittest.main()
