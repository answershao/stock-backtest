from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd


def parse_stock_pool(raw: str | Iterable[str]) -> list[str]:
    if isinstance(raw, str):
        codes = [code.strip() for code in raw.split(",")]
        return [code for code in codes if code]

    codes = [str(code).strip() for code in raw]
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


def load_stock_name_map(path: str | Path) -> dict[str, str]:
    data = pd.read_csv(path)
    if "ts_code" not in data.columns or "name" not in data.columns:
        return {}
    subset = data[["ts_code", "name"]].dropna()
    if subset.empty:
        return {}
    subset["ts_code"] = subset["ts_code"].astype(str).str.strip()
    subset["name"] = subset["name"].astype(str).str.strip()
    subset = subset[(subset["ts_code"] != "") & (subset["name"] != "")]
    return dict(zip(subset["ts_code"], subset["name"]))


def resolve_stock_pool(args: argparse.Namespace) -> list[str]:
    if args.stock_pool_file:
        return load_stock_pool_file(args.stock_pool_file)
    raw = args.stock_pool
    if not raw:
        return []
    return parse_stock_pool(raw)
