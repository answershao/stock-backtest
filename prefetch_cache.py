from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.tushare import create_tushare_pro, prefetch_tushare_strategy_cache
from src.stock_pool import resolve_stock_pool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="拉取并更新 Tushare 本地缓存")
    parser.add_argument("--stock-pool", help="股票池，逗号分隔，例如 600519.SH,000858.SZ")
    parser.add_argument("--stock-pool-file", help="股票池文件，支持 csv，需包含 ts_code 列")
    parser.add_argument("--token", default=os.getenv("TUSHARE_TOKEN"), help="Tushare token，默认读取环境变量 TUSHARE_TOKEN")
    parser.add_argument("--http-url", default="https://tu.brze.top", help="Tushare HTTP 地址，默认 https://tu.brze.top")
    parser.add_argument("--end-date", help="缓存截止日期，格式 YYYYMMDD；默认到今天")
    parser.add_argument(
        "--cache-dir",
        default="artifacts/tushare_cache",
        help="Tushare 本地缓存目录，默认 artifacts/tushare_cache",
    )
    parser.add_argument(
        "--refresh-datasets",
        help="需要强制重拉的缓存数据集，逗号分隔，例如 report_rc,daily_basic",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.token:
        raise SystemExit("缺少 Tushare token。请传 --token 或设置环境变量 TUSHARE_TOKEN")
    stock_pool = resolve_stock_pool(args)
    if not stock_pool:
        raise SystemExit("股票池为空。请通过 --stock-pool 或 --stock-pool-file 传入至少一个 ts_code")

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    pro = create_tushare_pro(args.token, http_url=args.http_url)
    artifacts = prefetch_tushare_strategy_cache(
        pro,
        stock_pool=stock_pool,
        cache_dir=cache_dir,
        end_date=args.end_date,
        refresh_datasets=_parse_csv_option(args.refresh_datasets),
    )

    print("缓存完成")
    print("股票池数量:", len(stock_pool))
    print("交易日数量:", len(artifacts.trading_dates))
    print("缓存目录:")
    print(cache_dir.resolve())


def _parse_csv_option(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


if __name__ == "__main__":
    main()
