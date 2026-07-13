from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_config import DEFAULT_LOCAL_CONFIG_PATH, load_local_config
from src.plotting import build_expected_return_frame, plot_expected_return_frame
from src.stock_pool import load_stock_name_map, resolve_stock_pool


def build_parser(defaults: dict[str, Any] | None = None) -> argparse.ArgumentParser:
    defaults = defaults or {}
    parser = argparse.ArgumentParser(description="绘制历史三年年化收益率时序图")
    parser.add_argument(
        "--config",
        default=DEFAULT_LOCAL_CONFIG_PATH,
        help=f"本地配置文件路径，默认 {DEFAULT_LOCAL_CONFIG_PATH}",
    )
    parser.add_argument(
        "--start-date",
        default=defaults.get("start_date", "20150630"),
        help="起始日期，格式 YYYYMMDD，默认 20150630",
    )
    parser.add_argument(
        "--cache-dir",
        default=defaults.get("cache_dir", "artifacts/tushare_cache"),
        help="缓存目录，默认 artifacts/tushare_cache",
    )
    parser.add_argument(
        "--output",
        default=defaults.get("output", "artifacts/expected_return"),
        help="输出目录，默认 artifacts/expected_return",
    )
    return parser


def main() -> None:
    args = parse_args()
    stock_pool = resolve_stock_pool(args)
    if not stock_pool:
        raise SystemExit("股票池为空。请在 config.local.json 中配置 stock_pool")

    end_date = pd.Timestamp.now().strftime("%Y%m%d")
    output_dir = Path(args.output) if args.output else Path("artifacts/expected_return")
    output_dir.mkdir(parents=True, exist_ok=True)
    stock_name_map = _load_stock_name_map(args)
    rows: list[dict[str, Any]] = []

    print("股票池数量:", len(stock_pool))
    print("开始日期:", args.start_date)
    print("结束日期:", end_date)
    print("输出目录:", output_dir)

    for ts_code in stock_pool:
        stock_name = stock_name_map.get(ts_code, "")
        frame = build_expected_return_frame(
            ts_code=ts_code,
            start_date=args.start_date,
            end_date=end_date,
            cache_dir=args.cache_dir,
        )
        latest = frame.dropna(
            subset=["mean_reversion_return_3y", "consensus_cagr_3y", "expected_return_3y"]
        ).iloc[-1]
        output = output_dir / f"expected_return_{ts_code}.png"

        if stock_name:
            print("股票:", f"{ts_code} {stock_name}")
        else:
            print("股票:", ts_code)
        print("样本交易日数:", len(frame))
        print("最新交易日:", latest["date"].strftime("%Y%m%d"))
        print(f"三年均值回归年化收益率: {latest['mean_reversion_return_3y']:.2%}")
        print(f"卖方三年 CAGR: {latest['consensus_cagr_3y']:.2%}")
        print(f"期望三年年化收益率: {latest['expected_return_3y']:.2%}")

        plot_expected_return_frame(
            frame,
            ts_code=ts_code,
            stock_name=stock_name,
            start_date=args.start_date,
            end_date=end_date,
            output=output,
        )
        print("图片已保存:", output)
        print()

        rows.append(
            {
                "ts_code": ts_code,
                "stock_name": stock_name,
                "sample_trade_days": len(frame),
                "latest_trade_date": latest["date"].strftime("%Y%m%d"),
                "mean_reversion_return_3y": latest["mean_reversion_return_3y"],
                "consensus_cagr_3y": latest["consensus_cagr_3y"],
                "expected_return_3y": latest["expected_return_3y"],
                "output_png": str(output),
            }
        )

    summary_path = output_dir / "expected_return_summary.csv"
    pd.DataFrame(rows).to_csv(summary_path, index=False, encoding="utf-8-sig")
    print("汇总 CSV 已保存:", summary_path)


def _load_cli_defaults(argv: list[str] | None = None) -> dict[str, Any]:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=DEFAULT_LOCAL_CONFIG_PATH)
    known_args, _ = bootstrap.parse_known_args(argv)
    return load_local_config(known_args.config)


def _load_stock_name_map(args: argparse.Namespace) -> dict[str, str]:
    stock_pool_file = getattr(args, "stock_pool_file", None)
    if not stock_pool_file:
        return {}
    return load_stock_name_map(stock_pool_file)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    defaults = _load_cli_defaults(argv)
    args = build_parser(defaults).parse_args(argv)
    merged = {
        "config": args.config,
        "stock_pool": defaults.get("stock_pool"),
        "stock_pool_file": defaults.get("stock_pool_file"),
        "start_date": args.start_date,
        "cache_dir": args.cache_dir,
        "output": args.output,
    }
    return argparse.Namespace(**merged)


if __name__ == "__main__":
    main()
