import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import pandas as pd

from plot_expected_return import _load_cli_defaults as load_plot_cli_defaults
from plot_expected_return import _resolve_latest_reason, _resolve_latest_trade_date, _resolve_latest_valid_row
from plot_expected_return import build_parser as build_plot_parser
from prefetch_cache import _load_cli_defaults, build_parser, parse_args
from src.local_config import load_local_config
from src.stock_pool import resolve_stock_pool


class RunTushareStrategyCliTest(unittest.TestCase):
    def test_load_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.local.json"
            path.write_text('{"token":"abc","stock_pool":{"600519.SH":"贵州茅台","000858.SZ":"五粮液"}}', encoding="utf-8")

            result = load_local_config(path)

        self.assertEqual(result["token"], "abc")
        self.assertEqual(result["stock_pool"], {"600519.SH": "贵州茅台", "000858.SZ": "五粮液"})

    def test_build_parser_uses_local_config_defaults(self) -> None:
        args = build_parser().parse_args([])
        self.assertIsNotNone(args)

    def test_parse_args_uses_local_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.local.json"
            path.write_text(
                '{"token":"abc","stock_pool":{"600519.SH":"贵州茅台"},"cache_dir":"tmp/cache","http_url":"https://example.com","market_data_cutoff_time":"17:30"}',
                encoding="utf-8",
            )

            args = parse_args(["--config", str(path)])

        self.assertEqual(args.token, "abc")
        self.assertEqual(args.stock_pool, {"600519.SH": "贵州茅台"})
        self.assertEqual(args.cache_dir, "tmp/cache")
        self.assertEqual(args.http_url, "https://example.com")
        self.assertEqual(args.market_data_cutoff_time, "17:30")

    def test_parse_args_cli_overrides_runtime_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.local.json"
            path.write_text(
                '{"refresh_datasets":"daily_basic"}',
                encoding="utf-8",
            )

            args = parse_args(
                [
                    "--config",
                    str(path),
                    "--refresh-datasets",
                    "report_rc",
                ]
            )

        self.assertEqual(args.refresh_datasets, "report_rc")

    def test_parse_args_supports_validate_only(self) -> None:
        args = parse_args(["--validate-only"])

        self.assertTrue(args.validate_only)

    def test_plot_parser_uses_local_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.local.json"
            path.write_text(
                '{"stock_pool":{"000858.SZ":"五粮液"},"start_date":"20180101","cache_dir":"tmp/cache","output":"tmp/out"}',
                encoding="utf-8",
            )

            defaults = load_plot_cli_defaults(["--config", str(path)])
            args = build_plot_parser(defaults).parse_args(["--config", str(path)])

        self.assertEqual(args.start_date, "20180101")
        self.assertEqual(args.cache_dir, "tmp/cache")
        self.assertEqual(args.output, "tmp/out")

    def test_resolve_stock_pool_from_dict(self) -> None:
        result = resolve_stock_pool(
            Namespace(
                stock_pool={"600519.SH": "贵州茅台", "000858.SZ": "五粮液"},
            )
        )

        self.assertEqual(result, ["600519.SH", "000858.SZ"])

    def test_plot_summary_helpers_handle_missing_valid_rows(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2024-01-02"),
                    "mean_reversion_return_3y": None,
                    "consensus_cagr_3y": None,
                    "expected_return_3y": None,
                    "reason": "target_pe_missing",
                }
            ]
        )

        self.assertIsNone(_resolve_latest_valid_row(frame))
        self.assertEqual(_resolve_latest_trade_date(frame), "20240102")
        self.assertEqual(_resolve_latest_reason(frame), "target_pe_missing")


if __name__ == "__main__":
    unittest.main()
