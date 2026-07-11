"""
研究版回测入口脚本

执行方式:
    python3 main.py
    python3 main.py warm-cache
"""

from __future__ import annotations

import argparse

from stock_backtest.app import run_application, warm_market_cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        default="backtest",
        choices=["backtest", "warm-cache"],
        help="backtest: 执行回测；warm-cache: 预热股票池日线/分红缓存",
    )
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="仅对 warm-cache 生效，强制全量重拉并覆盖本地缓存",
    )
    args = parser.parse_args()

    if args.command == "warm-cache":
        warm_market_cache(force_full=args.force_full)
        return

    run_application()


if __name__ == "__main__":
    main()
