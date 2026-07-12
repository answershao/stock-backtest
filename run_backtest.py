from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.data.tushare import run_tushare_expected_return_backtest, write_backtest_artifacts
from backtest.stock_pool import resolve_stock_pool
from backtest.strategy import StrategyConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行基于本地缓存数据的三年期望收益率回测")
    parser.add_argument("--stock-pool", help="股票池，逗号分隔，例如 600519.SH,000858.SZ")
    parser.add_argument("--stock-pool-file", help="股票池文件，支持 csv，需包含 ts_code 列")
    parser.add_argument("--start-date", required=True, help="回测开始日期，格式 YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="回测结束日期，格式 YYYYMMDD")
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0, help="初始资金，默认 1000000")
    parser.add_argument("--output-dir", default="artifacts/tushare_backtest", help="输出目录，默认 artifacts/tushare_backtest")
    parser.add_argument("--cache-dir", default="artifacts/tushare_cache", help="Tushare 本地缓存目录，默认 artifacts/tushare_cache")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    stock_pool = resolve_stock_pool(args)
    if not stock_pool:
        raise SystemExit("股票池为空。请通过 --stock-pool 或 --stock-pool-file 传入至少一个 ts_code")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts = run_tushare_expected_return_backtest(
        None,
        stock_pool=stock_pool,
        start_date=args.start_date,
        end_date=args.end_date,
        strategy_config=StrategyConfig(initial_cash=args.initial_cash),
        cache_dir=args.cache_dir,
    )
    output_paths = write_backtest_artifacts(artifacts, output_dir=output_dir)

    final_row = artifacts.backtest_result.portfolio_history.iloc[-1]
    print("回测完成")
    print("股票池数量:", len(stock_pool))
    print("起始交易日:", artifacts.backtest_result.portfolio_history.iloc[0]["date"])
    print("调仓日:", ", ".join(date.strftime("%Y-%m-%d") for date in artifacts.rebalance_dates) or "无")
    print("期末总资产:", round(float(final_row["equity"]), 2))
    print("期末现金:", round(float(final_row["cash"]), 2))
    print("期末持仓数:", int(final_row["positions"]))
    print("输出文件:")
    print(output_paths.portfolio_path)
    print(output_paths.trades_path)
    print(output_paths.holdings_path)
    print(output_paths.signals_path)
    print("缓存目录:")
    print(Path(args.cache_dir).resolve())


if __name__ == "__main__":
    main()
