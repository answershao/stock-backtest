from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.tushare import create_tushare_pro, prefetch_tushare_cache
from src.data.tushare_cache_validator import validate_tushare_cache
from src.local_config import DEFAULT_LOCAL_CONFIG_PATH, load_local_config
from src.stock_pool import resolve_stock_pool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="拉取并更新 Tushare 本地缓存")
    parser.add_argument(
        "--config",
        default=DEFAULT_LOCAL_CONFIG_PATH,
        help=f"本地配置文件路径，默认 {DEFAULT_LOCAL_CONFIG_PATH}",
    )
    parser.add_argument(
        "--refresh-datasets",
        help="需要强制重拉的缓存数据集，逗号分隔，例如 report_rc,daily_basic",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="只校验现有缓存，不发起下载",
    )
    return parser


def main() -> None:
    args = parse_args()
    stock_pool = resolve_stock_pool(args)
    if not stock_pool:
        raise SystemExit("股票池为空。请在 config.local.json 中配置 stock_pool 或 stock_pool_file")

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if args.validate_only:
        _validate_or_raise(cache_dir=cache_dir, stock_pool=stock_pool)
        print("缓存校验通过")
        print("股票池数量:", len(stock_pool))
        print("缓存目录:")
        print(cache_dir.resolve())
        return

    if not args.token:
        raise SystemExit("缺少 Tushare token。请在 config.local.json 中配置 token，或设置环境变量 TUSHARE_TOKEN")

    pro = create_tushare_pro(args.token, http_url=args.http_url)
    artifacts = prefetch_tushare_cache(
        pro,
        stock_pool=stock_pool,
        cache_dir=cache_dir,
        refresh_datasets=_parse_csv_option(args.refresh_datasets),
    )
    _validate_or_raise(cache_dir=cache_dir, stock_pool=stock_pool)

    print("缓存完成并校验通过")
    print("股票池数量:", len(stock_pool))
    print("交易日数量:", len(artifacts.trading_dates))
    print("缓存目录:")
    print(cache_dir.resolve())


def _parse_csv_option(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _validate_or_raise(*, cache_dir: Path, stock_pool: list[str]) -> None:
    result = validate_tushare_cache(cache_dir=cache_dir, stock_pool=stock_pool)
    if result.ok:
        return
    details = "\n".join(f"- {issue.path}: {issue.message}" for issue in result.issues[:20])
    suffix = "\n- ..." if len(result.issues) > 20 else ""
    raise SystemExit(f"缓存校验失败，共 {len(result.issues)} 个问题:\n{details}{suffix}")


def _load_cli_defaults(argv: list[str] | None = None) -> dict[str, object]:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=DEFAULT_LOCAL_CONFIG_PATH)
    known_args, _ = bootstrap.parse_known_args(argv)
    return load_local_config(known_args.config)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    defaults = _load_cli_defaults(argv)
    merged = {
        "config": args.config,
        "stock_pool": defaults.get("stock_pool"),
        "stock_pool_file": defaults.get("stock_pool_file"),
        "token": defaults.get("token") or os.getenv("TUSHARE_TOKEN"),
        "http_url": defaults.get("http_url", "https://tu.brze.top"),
        "cache_dir": defaults.get("cache_dir", "artifacts/tushare_cache"),
        "refresh_datasets": args.refresh_datasets or defaults.get("refresh_datasets"),
        "validate_only": args.validate_only,
    }
    return argparse.Namespace(**merged)


if __name__ == "__main__":
    main()
