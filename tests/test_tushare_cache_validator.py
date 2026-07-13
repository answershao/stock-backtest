import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data.tushare_cache_validator import validate_tushare_cache


class TushareCacheValidatorTest(unittest.TestCase):
    def test_validate_tushare_cache_accepts_valid_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            self._write_csv(
                cache_root / "trade_cal" / "full__is_open_1.csv",
                [
                    {"cal_date": "20240102", "is_open": 1},
                    {"cal_date": "20240103", "is_open": 1},
                ],
            )
            self._write_csv(
                cache_root / "daily_basic" / "600519.SH__pe_ttm__close.csv",
                [
                    {"ts_code": "600519.SH", "trade_date": "20240102", "pe_ttm": 20.0, "close": 10.0},
                    {"ts_code": "600519.SH", "trade_date": "20240103", "pe_ttm": 21.0, "close": 11.0},
                ],
            )
            self._write_csv(
                cache_root / "report_rc" / "600519.SH.csv",
                [
                    {
                        "report_date": "20240102",
                        "report_title": "标题A",
                        "report_type": "买入",
                        "classify": "公司",
                        "org_name": "机构A",
                        "author_name": "作者甲",
                        "quarter": "2025Q4",
                        "eps": 1.0,
                    },
                    {
                        "report_date": "20240102",
                        "report_title": "标题A",
                        "report_type": "买入",
                        "classify": "公司",
                        "org_name": "机构A",
                        "author_name": "作者甲",
                        "quarter": "2026Q4",
                        "eps": 1.1,
                    },
                    {
                        "report_date": "20240102",
                        "report_title": "标题A",
                        "report_type": "买入",
                        "classify": "公司",
                        "org_name": "机构A",
                        "author_name": "作者甲",
                        "quarter": "2027Q4",
                        "eps": 1.2,
                    },
                ],
            )
            self._write_csv(
                cache_root / "fina_indicator" / "600519.SH.csv",
                [
                    {"ann_date": "20240103", "end_date": "20231231", "eps": 1.0},
                ],
            )
            self._write_csv(
                cache_root / "dividend" / "600519.SH.csv",
                [
                    {
                        "ts_code": "600519.SH",
                        "ex_date": "20240103",
                        "cash_div": 1.0,
                        "stk_div": 0.8,
                        "stk_bo_rate": 0.3,
                        "stk_co_rate": 0.5,
                        "div_proc": "实施",
                    },
                ],
            )

            result = validate_tushare_cache(cache_dir=cache_root, stock_pool=["600519.SH"])

        self.assertTrue(result.ok)
        self.assertEqual(result.issues, ())

    def test_validate_tushare_cache_reports_invalid_cached_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            self._write_csv(
                cache_root / "trade_cal" / "full__is_open_1.csv",
                [
                    {"cal_date": "20240103", "is_open": 1},
                    {"cal_date": "20240102", "is_open": 0},
                ],
            )
            self._write_csv(
                cache_root / "daily_basic" / "600519.SH__pe_ttm__close.csv",
                [
                    {"ts_code": "000858.SZ", "trade_date": "20240104", "pe_ttm": 10.0, "close": 10.0},
                ],
            )

            result = validate_tushare_cache(
                cache_dir=cache_root,
                stock_pool=["600519.SH"],
                required_datasets=("trade_cal", "daily_basic"),
            )

        self.assertFalse(result.ok)
        messages = "\n".join(issue.message for issue in result.issues)
        self.assertIn("is_open 存在非 1 的记录", messages)
        self.assertIn("cal_date 未按升序排列", messages)
        self.assertIn("ts_code 与文件名不一致", messages)
        self.assertIn("存在非交易日数据", messages)

    def test_validate_tushare_cache_reports_suspiciously_truncated_report_rc(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            rows = [
                {
                    "report_date": f"2024{(idx % 12) + 1:02d}01",
                    "report_title": f"title_{idx}",
                    "report_type": "买入",
                    "classify": "公司",
                    "quarter": f"202{idx % 4}Q4",
                    "org_name": f"org_{idx}",
                    "author_name": f"author_{idx}",
                    "eps": float(idx + 1),
                }
                for idx in range(3000)
            ]
            self._write_csv(cache_root / "report_rc" / "600519.SH.csv", rows)

            result = validate_tushare_cache(
                cache_dir=cache_root,
                stock_pool=["600519.SH"],
                required_datasets=("report_rc",),
            )

        self.assertFalse(result.ok)
        messages = "\n".join(issue.message for issue in result.issues)
        self.assertIn("可能命中分页截断", messages)

    def test_validate_tushare_cache_reports_report_rc_groups_with_too_few_quarters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir)
            self._write_csv(
                cache_root / "report_rc" / "600519.SH.csv",
                [
                    {
                        "report_date": "20240102",
                        "report_title": "标题A",
                        "report_type": "买入",
                        "classify": "公司",
                        "org_name": "机构A",
                        "author_name": "作者甲",
                        "quarter": "2026Q4",
                        "eps": 1.0,
                    },
                    {
                        "report_date": "20240102",
                        "report_title": "标题A",
                        "report_type": "买入",
                        "classify": "公司",
                        "org_name": "机构A",
                        "author_name": "作者甲",
                        "quarter": "2027Q4",
                        "eps": 1.1,
                    },
                ],
            )

            result = validate_tushare_cache(
                cache_dir=cache_root,
                stock_pool=["600519.SH"],
                required_datasets=("report_rc",),
            )

        self.assertFalse(result.ok)
        messages = "\n".join(issue.message for issue in result.issues)
        self.assertIn("季度预测数少于 3", messages)

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(path, index=False)


if __name__ == "__main__":
    unittest.main()
