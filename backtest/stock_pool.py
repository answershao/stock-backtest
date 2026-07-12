from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def parse_stock_pool(raw: str) -> list[str]:
    codes = [code.strip() for code in raw.split(",")]
    return [code for code in codes if code]


def load_stock_pool_file(path: str | Path) -> list[str]:
    data = pd.read_csv(path)
    if "ts_code" not in data.columns:
        raise SystemExit("股票池文件缺少 ts_code 列")
    series = data["ts_code"].dropna().astype(str).str.strip()
    stock_pool = [code for code in series.tolist() if code]
    if not stock_pool:
        raise SystemExit("股票池文件中没有有效 ts_code")
    return stock_pool


def resolve_stock_pool(args: Any) -> list[str]:
    if getattr(args, "stock_pool_file", None):
        return load_stock_pool_file(args.stock_pool_file)
    raw = getattr(args, "stock_pool", None)
    if not raw:
        return []
    return parse_stock_pool(raw)
