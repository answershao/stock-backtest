from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.plotting import build_expected_return_frame, plot_expected_return_frame


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="绘制历史三年年化收益率时序图")
    parser.add_argument("--ts-code", default="600519.SH", help="股票代码，默认 600519.SH")
    parser.add_argument("--start-date", default="20150630", help="起始日期，格式 YYYYMMDD，默认 20150630")
    parser.add_argument("--cache-dir", default="artifacts/tushare_cache", help="缓存目录，默认 artifacts/tushare_cache")
    parser.add_argument("--output", default=None, help="输出图片路径，默认 artifacts/expected_return_<ts-code>.png")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    end_date = pd.Timestamp.now().strftime("%Y%m%d")
    frame = build_expected_return_frame(
        ts_code=args.ts_code,
        start_date=args.start_date,
        end_date=end_date,
        cache_dir=args.cache_dir,
    )
    latest = frame.dropna(subset=["mean_reversion_return_3y", "consensus_cagr_3y", "expected_return_3y"]).iloc[-1]

    print("股票:", args.ts_code)
    print("开始日期:", args.start_date)
    print("结束日期:", end_date)
    print("样本交易日数:", len(frame))
    print("最新交易日:", latest["date"].strftime("%Y%m%d"))
    print(f"三年均值回归年化收益率: {latest['mean_reversion_return_3y']:.2%}")
    print(f"卖方三年 CAGR: {latest['consensus_cagr_3y']:.2%}")
    print(f"期望三年年化收益率: {latest['expected_return_3y']:.2%}")

    output = Path(args.output) if args.output else Path(f"artifacts/expected_return_{args.ts_code}.png")
    plot_expected_return_frame(
        frame,
        ts_code=args.ts_code,
        start_date=args.start_date,
        end_date=end_date,
        output=output,
    )
    print("图片已保存:", output)


if __name__ == "__main__":
    main()
