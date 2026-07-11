"""
回测输入装配模块
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from stock_backtest.core import config as cfg
from stock_backtest.core.models import BacktestInputs, MarketContext
from stock_backtest.core.scheduler import generate_rebalance_dates
from stock_backtest.data.data import (
    fetch_benchmark,
    fetch_daily_quotes,
    fetch_dividends,
    fetch_research_fundamentals,
    fetch_trade_calendar,
    load_fundamentals_csv,
)


def load_fundamentals_for_mode() -> Optional[pd.DataFrame]:
    if cfg.SYSTEM.strategy_mode != "research_quant":
        return None

    csv_path = Path(cfg.DATA_SOURCE.fundamental_data_path)
    if csv_path.exists():
        print(f"使用本地基本面文件: {csv_path}")
        return load_fundamentals_csv(csv_path)

    print("本地基本面文件不存在，改为从 Tushare 拉取研究版基本面数据")
    return fetch_research_fundamentals(cfg.UNIVERSE.stock_codes, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)


def load_backtest_inputs() -> BacktestInputs:
    print("开始获取交易日历...")
    trade_dates = fetch_trade_calendar(cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)

    print("开始获取股票行情...")
    quotes = fetch_daily_quotes(cfg.UNIVERSE.stock_codes, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)

    print("开始获取分红数据...")
    dividends = fetch_dividends(cfg.UNIVERSE.stock_codes)

    print("开始获取基准指数...")
    benchmark = fetch_benchmark(cfg.BACKTEST.benchmark_index, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)

    print("开始获取/加载基本面数据...")
    fundamentals = load_fundamentals_for_mode()

    return BacktestInputs(
        quotes=quotes,
        dividends=dividends,
        trade_dates=trade_dates,
        benchmark_df=benchmark,
        fundamentals=fundamentals,
    )


def resolve_candidate_codes(quotes: dict, fundamentals: Optional[pd.DataFrame]) -> list:
    if cfg.UNIVERSE.candidate_pool_mode == "whitelist":
        return list(cfg.UNIVERSE.stock_codes)
    if cfg.UNIVERSE.candidate_pool_mode == "all_quotes":
        return sorted(quotes.keys())
    if fundamentals is not None and not fundamentals.empty:
        return sorted(fundamentals["code"].dropna().astype(str).unique().tolist())
    return list(cfg.UNIVERSE.stock_codes)


def build_dividend_map(dividends: dict) -> dict:
    result = {}
    for code, df in dividends.items():
        event_map = {}
        if df is None or df.empty:
            result[code] = event_map
            continue
        for _, row in df.iterrows():
            trade_date = row["date"]
            if isinstance(trade_date, pd.Timestamp):
                trade_date = trade_date.date()
            event_map[trade_date] = (
                float(row.get("cash_dividend", 0.0) or 0.0),
                float(row.get("bonus_ratio", 0.0) or 0.0),
                float(row.get("transfer_ratio", 0.0) or 0.0),
            )
        result[code] = event_map
    return result


def build_price_index(quotes: dict) -> dict:
    return {code: dict(zip(df["date"], df["close"])) for code, df in quotes.items()}


def build_benchmark_map(benchmark_df: pd.DataFrame) -> dict:
    if benchmark_df is None or benchmark_df.empty:
        return {}
    return dict(zip(benchmark_df["date"], benchmark_df["close"]))


def build_market_context(inputs: BacktestInputs) -> MarketContext:
    start = date.fromisoformat(cfg.BACKTEST.start_date)
    end = date.fromisoformat(cfg.BACKTEST.end_date)
    candidate_codes = resolve_candidate_codes(inputs.quotes, inputs.fundamentals)
    sorted_trade_dates = sorted(d for d in inputs.trade_dates if start <= d <= end)
    if not sorted_trade_dates:
        raise RuntimeError("回测区间内无交易日数据")

    return MarketContext(
        start=start,
        end=end,
        candidate_codes=candidate_codes,
        stock_names=dict(cfg.UNIVERSE.stock_name_map),
        price_index=build_price_index(inputs.quotes),
        dividend_map=build_dividend_map(inputs.dividends),
        benchmark_map=build_benchmark_map(inputs.benchmark_df),
        sorted_trade_dates=sorted_trade_dates,
        rebalance_dates=generate_rebalance_dates(start, end, cfg.BACKTEST.rebalance_schedule, inputs.trade_dates),
    )
