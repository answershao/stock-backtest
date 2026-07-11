"""
数据获取门面模块

- 对外暴露稳定的 fetch_* / load_* 接口
- 内部拆分为 Tushare 原始抓取层 与 字段映射层
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_backtest.data.data_mapping import (
    load_fundamentals_csv_frame,
    merge_research_fundamentals,
    normalize_benchmark_frame,
    normalize_dividend_frame,
    normalize_quote_frame,
    normalize_trade_calendar,
    standardize_fundamentals,
)
from stock_backtest.data.tushare_client import (
    fetch_benchmark_raw,
    fetch_daily_basic_raw,
    fetch_daily_quotes_raw,
    fetch_dividends_raw,
    fetch_fina_indicator_raw,
    fetch_stock_basic_raw,
    fetch_trade_calendar_raw,
)


def fetch_daily_quotes(symbols, start, end):
    raw_result = fetch_daily_quotes_raw(symbols, start, end)
    result = {}
    for code, raw_df in raw_result.items():
        try:
            df = normalize_quote_frame(raw_df)
            if df.empty:
                print("  %s 无日线数据，跳过" % code)
                continue
            result[code] = df
            print("  %s 日线数据获取完成 (%s 条)" % (code, len(df)))
        except Exception as exc:
            print("  %s 日线数据获取失败: %s" % (code, exc))
    return result


def fetch_dividends(symbols):
    raw_result = fetch_dividends_raw(symbols)
    result = {}
    empty = pd.DataFrame(columns=["date", "cash_dividend", "bonus_ratio", "transfer_ratio"])
    for code, raw_df in raw_result.items():
        try:
            df = normalize_dividend_frame(raw_df)
            result[code] = df if not df.empty else empty.copy()
            print("  %s 分红数据获取完成 (%s 条)" % (code, len(result[code])))
        except Exception as exc:
            print("  %s 分红数据获取失败: %s，默认为无分红" % (code, exc))
            result[code] = empty.copy()
    return result


def fetch_trade_calendar(start, end):
    trade_dates = normalize_trade_calendar(fetch_trade_calendar_raw(start, end))
    print("  交易日历获取完成 (%s 个交易日)" % len(trade_dates))
    return trade_dates


def fetch_benchmark(index_code, start, end):
    try:
        df = normalize_benchmark_frame(fetch_benchmark_raw(index_code, start, end))
        print("  基准指数 %s 获取完成 (%s 条)" % (index_code, len(df)))
        return df
    except Exception as exc:
        print("  基准指数获取失败: %s，将跳过基准对比" % exc)
        return pd.DataFrame(columns=["date", "close"])


def fetch_research_fundamentals(symbols, start, end):
    stock_basic = fetch_stock_basic_raw()
    if stock_basic is None or stock_basic.empty:
        raise RuntimeError("stock_basic 获取失败")

    stock_basic = stock_basic.copy()
    stock_basic["code"] = stock_basic["symbol"].astype(str)
    stock_basic["listing_date"] = pd.to_datetime(stock_basic["list_date"], errors="coerce").dt.date
    stock_basic = stock_basic[stock_basic["code"].isin(symbols)].copy()

    frames = []
    for code in symbols:
        try:
            daily_basic = fetch_daily_basic_raw(code, start, end)
            fina = fetch_fina_indicator_raw(code, start, end)
            meta = stock_basic[stock_basic["code"] == code]
            if meta.empty:
                continue

            merged = merge_research_fundamentals(
                daily_basic=daily_basic,
                fina=fina,
                code=code,
                industry=meta["industry"].iloc[0],
                listing_date=meta["listing_date"].iloc[0],
            )
            if merged.empty:
                continue
            frames.append(merged)
            print("  %s 基本面数据获取完成 (%s 条)" % (code, len(merged)))
        except Exception as exc:
            print("  %s 基本面数据获取失败: %s" % (code, exc))

    if not frames:
        raise RuntimeError("未获取到任何研究版基本面数据")
    return standardize_fundamentals(pd.concat(frames, ignore_index=True))


def load_fundamentals_csv(path):
    return standardize_fundamentals(load_fundamentals_csv_frame(Path(path)))
