import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data.tushare_analysis import (
    CachedStockAnalysisFrames,
    ExpectedReturnTimeseriesRequest,
    build_expected_return_timeseries,
)


class TushareAnalysisTest(unittest.TestCase):
    def test_build_expected_return_timeseries_uses_indexed_cache_slices(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            self._write_csv(
                cache_root / "trade_cal" / "full__is_open_1.csv",
                [
                    {"cal_date": "20240102", "is_open": 1},
                    {"cal_date": "20240103", "is_open": 1},
                    {"cal_date": "20240104", "is_open": 1},
                ],
            )
            self._write_csv(
                cache_root / "daily_basic" / "600519.SH__pe_ttm__close.csv",
                [
                    {"ts_code": "600519.SH", "trade_date": "20230102", "pe_ttm": 10.0, "close": 90.0},
                    {"ts_code": "600519.SH", "trade_date": "20230103", "pe_ttm": 11.0, "close": 91.0},
                    {"ts_code": "600519.SH", "trade_date": "20230104", "pe_ttm": 12.0, "close": 92.0},
                    {"ts_code": "600519.SH", "trade_date": "20230105", "pe_ttm": 13.0, "close": 93.0},
                    {"ts_code": "600519.SH", "trade_date": "20230106", "pe_ttm": 14.0, "close": 94.0},
                    {"ts_code": "600519.SH", "trade_date": "20230109", "pe_ttm": 15.0, "close": 95.0},
                    {"ts_code": "600519.SH", "trade_date": "20230110", "pe_ttm": 16.0, "close": 96.0},
                    {"ts_code": "600519.SH", "trade_date": "20230111", "pe_ttm": 17.0, "close": 97.0},
                    {"ts_code": "600519.SH", "trade_date": "20230112", "pe_ttm": 18.0, "close": 98.0},
                    {"ts_code": "600519.SH", "trade_date": "20230113", "pe_ttm": 19.0, "close": 99.0},
                    {"ts_code": "600519.SH", "trade_date": "20230116", "pe_ttm": 20.0, "close": 100.0},
                    {"ts_code": "600519.SH", "trade_date": "20230117", "pe_ttm": 21.0, "close": 101.0},
                    {"ts_code": "600519.SH", "trade_date": "20240102", "pe_ttm": 22.0, "close": 100.0},
                    {"ts_code": "600519.SH", "trade_date": "20240103", "pe_ttm": 23.0, "close": 100.0},
                    {"ts_code": "600519.SH", "trade_date": "20240104", "pe_ttm": 24.0, "close": 102.0},
                ],
            )
            self._write_csv(
                cache_root / "report_rc" / "600519.SH.csv",
                [
                    {"org_name": "A", "quarter": "2026Q4", "report_date": "20240102", "eps": 20.0},
                    {"org_name": "B", "quarter": "2026Q4", "report_date": "20240103", "eps": 22.0},
                ],
            )
            self._write_csv(
                cache_root / "fina_indicator" / "600519.SH.csv",
                [
                    {"ann_date": "20231231", "end_date": "20231231", "eps": 10.0},
                ],
            )

            frame = build_expected_return_timeseries(
                ExpectedReturnTimeseriesRequest(
                    ts_code="600519.SH",
                    start_date="20240102",
                    end_date="20240104",
                    cache_dir=cache_root,
                    pe_history_years=10,
                )
            )

        self.assertEqual(frame["date"].dt.strftime("%Y%m%d").tolist(), ["20240102", "20240103", "20240104"])
        self.assertEqual(frame["close"].tolist(), [100.0, 100.0, 102.0])
        self.assertEqual(frame["valid"].tolist(), [True, True, True])
        self.assertEqual(frame["reason"].tolist(), [None, None, None])

    def test_cached_stock_analysis_frames_resolves_as_of_values(self) -> None:
        daily_basic = pd.DataFrame(
            [
                {"date": pd.Timestamp("2024-01-02"), "pe_ttm": 10.0, "close": 100.0},
                {"date": pd.Timestamp("2024-01-03"), "pe_ttm": 11.0, "close": 101.0},
            ]
        )
        report_rc = pd.DataFrame(
            [
                {"report_date": pd.Timestamp("2024-01-02"), "quarter": "2026Q4", "org_name": "A", "eps": 20.0},
                {"report_date": pd.Timestamp("2024-01-03"), "quarter": "2026Q4", "org_name": "B", "eps": 21.0},
            ]
        )
        fina_indicator = pd.DataFrame(
            [
                {"ann_date": pd.Timestamp("2023-12-31"), "end_date": pd.Timestamp("2023-12-31"), "eps": 10.0},
            ]
        )
        analysis = CachedStockAnalysisFrames(
            daily_basic=daily_basic,
            report_rc=report_rc,
            fina_indicator=fina_indicator,
            daily_basic_dates=daily_basic["date"].to_numpy(),
            report_dates=report_rc["report_date"].to_numpy(),
            fina_ann_dates=fina_indicator["ann_date"].to_numpy(),
        )

        current_pe, pe_history = analysis.resolve_current_pe_and_history(
            as_of_ts=pd.Timestamp("2024-01-03"),
            pe_history_years=10,
        )
        report_as_of = analysis.resolve_report_as_of(pd.Timestamp("2024-01-02"))
        base_quarter, ann_date, base_eps = analysis.resolve_base_annual_eps(pd.Timestamp("2024-01-03"))

        self.assertEqual(current_pe, 11.0)
        self.assertEqual(pe_history, [10.0, 11.0])
        self.assertEqual(len(report_as_of), 1)
        self.assertEqual(base_quarter, "2023Q4")
        self.assertEqual(ann_date, "20231231")
        self.assertEqual(base_eps, 10.0)
        self.assertEqual(analysis.resolve_close(pd.Timestamp("2024-01-03")), 101.0)

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(path, index=False)


if __name__ == "__main__":
    unittest.main()
