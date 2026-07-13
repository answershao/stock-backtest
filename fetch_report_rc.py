from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.tushare_expected_return import create_tushare_pro, fetch_report_rc_from_tushare
from src.local_config import DEFAULT_LOCAL_CONFIG_PATH, load_local_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="拉取单只股票的完整研报 report_rc 并导出 CSV")
    parser.add_argument(
        "--config",
        default=DEFAULT_LOCAL_CONFIG_PATH,
        help=f"本地配置文件路径，默认 {DEFAULT_LOCAL_CONFIG_PATH}",
    )
    parser.add_argument(
        "--ts-code",
        default="600809.SH",
        help="股票代码，例如 600519.SH",
    )
    parser.add_argument(
        "--start-date",
        default="20100101",
        help="起始日期，格式 YYYYMMDD，默认 20150101",
    )
    parser.add_argument(
        "--end-date",
        help="结束日期，格式 YYYYMMDD，默认今天",
    )
    parser.add_argument(
        "--output",
        help="输出 CSV 路径，默认 artifacts/report_rc/<ts_code>_<start>_<end>.csv",
    )
    return parser


def main() -> None:
    args = parse_args()
    if not args.ts_code:
        raise SystemExit("缺少 ts_code。请传入 --ts-code，或在 config.local.json 的 stock_pool 中只保留一只股票")
    if not args.token:
        raise SystemExit("缺少 Tushare token。请在 config.local.json 中配置 token，或设置环境变量 TUSHARE_TOKEN")

    output_path = Path(args.output) if args.output else _default_output_path(args.ts_code, args.start_date, args.end_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pro = create_tushare_pro(args.token, http_url=args.http_url)
    frame = fetch_report_rc_from_tushare(
        pro,
        ts_code=args.ts_code,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    frame = _sort_report_frame(frame)
    frame.to_csv(output_path, index=False, encoding="utf-8-sig")

    print("股票:", args.ts_code)
    print("开始日期:", args.start_date)
    print("结束日期:", args.end_date)
    print("研报行数:", len(frame))
    print("输出文件:", output_path.resolve())


def _default_output_path(ts_code: str, start_date: str, end_date: str) -> Path:
    return Path("artifacts/report_rc") / f"{ts_code}_{start_date}_{end_date}.csv"


def _sort_report_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    sort_columns = [column for column in ("report_date", "report_title", "quarter", "org_name") if column in frame.columns]
    if not sort_columns:
        return frame.reset_index(drop=True)
    return frame.sort_values(sort_columns).reset_index(drop=True)


def _load_cli_defaults(argv: list[str] | None = None) -> dict[str, object]:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=DEFAULT_LOCAL_CONFIG_PATH)
    known_args, _ = bootstrap.parse_known_args(argv)
    return load_local_config(known_args.config)


def _resolve_ts_code(cli_ts_code: str | None, stock_pool: object) -> str | None:
    if cli_ts_code:
        return cli_ts_code.strip() or None
    if not isinstance(stock_pool, dict):
        return None
    codes = [str(code).strip() for code in stock_pool.keys() if str(code).strip()]
    if len(codes) == 1:
        return codes[0]
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    defaults = _load_cli_defaults(argv)
    args = build_parser().parse_args(argv)
    end_date = args.end_date or pd.Timestamp.now().strftime("%Y%m%d")
    merged = {
        "config": args.config,
        "ts_code": _resolve_ts_code(args.ts_code, defaults.get("stock_pool")),
        "start_date": args.start_date,
        "end_date": end_date,
        "output": args.output,
        "token": defaults.get("token") or os.getenv("TUSHARE_TOKEN"),
        "http_url": defaults.get("http_url", "https://tu.brze.top"),
    }
    return argparse.Namespace(**merged)


if __name__ == "__main__":
    main()
