"""
数据获取模块 — 基于 AkShare
- 日线行情（后复权）
- 历史分红送配
- 交易日历
- 基准指数行情
"""

import time
import random
from datetime import date
import pandas as pd

try:
    import akshare as ak
except ImportError:
    raise ImportError("请先安装 akshare: pip install akshare")


def _retry(func, *args, max_retries=3, base_delay=3, **kwargs):
    """带随机退避的重试机制，用于应对 API 限流"""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt) + random.uniform(0, 2)
                print(f"    ⏳ 请求失败 ({e.__class__.__name__}), {wait:.1f}s 后重试...")
                time.sleep(wait)
            else:
                raise


def _symbol_prefix(code: str) -> str:
    """600xxx → sh600xxx, 000xxx → sz000xxx, 300xxx → sz300xxx"""
    if code.startswith(("6", "5")):
        return f"sh{code}"
    else:
        return f"sz{code}"


def fetch_daily_quotes(symbols: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """
    获取每只股票的后复权日线数据（新浪财经）。

    参数
    ----
    symbols : list[str]     股票代码列表，如 ["603288", "000538"]
    start : str             起始日期 "YYYYMMDD" 或 "YYYY-MM-DD"
    end : str               结束日期

    返回
    ----
    dict[str, DataFrame]    按股票代码索引的 DataFrame，列含:
        date, open, high, low, close, volume, amount, turnover
    """
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")

    result = {}
    for i, code in enumerate(symbols):
        try:
            # 请求间隔，避免被限流封 IP
            if i > 0:
                time.sleep(random.uniform(1.5, 4.0))
            sym = _symbol_prefix(code)
            df = _retry(
                ak.stock_zh_a_daily,
                symbol=sym,
                start_date=start_fmt,
                end_date=end_fmt,
                adjust="hfq",
            )
            if df is None or df.empty:
                print(f"  ⚠ {code} 无数据，跳过")
                continue
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df = df.sort_values("date").reset_index(drop=True)
            result[code] = df
            print(f"  ✓ {code} 日线数据获取完成 ({len(df)} 条)")
        except Exception as e:
            print(f"  ✗ {code} 获取失败: {e}")

    return result


def fetch_dividends(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """
    获取每只股票历史分红送配记录。

    返回
    ----
    dict[str, DataFrame]    列含:
        date (除权除息日), cash_dividend (每股派息),
        bonus_ratio (送股比例), transfer_ratio (转增比例)
    """
    result = {}
    for i, code in enumerate(symbols):
        try:
            if i > 0:
                time.sleep(random.uniform(0.5, 1.5))
            df = _retry(ak.stock_history_dividend_detail, symbol=code, indicator="分红")
            if df is None or df.empty:
                result[code] = pd.DataFrame(columns=["date", "cash_dividend", "bonus_ratio", "transfer_ratio"])
                continue
            # 只保留已实施的
            df = df[df["进度"] == "实施"].copy()
            # 列名映射
            df = df.rename(columns={
                "除权除息日": "date",
            })
            df["date"] = pd.to_datetime(df["date"]).dt.date
            # 送股/转增：原始值为每10股送/转多少股，转为每股比例
            # e.g. 送股=2.0 → bonus_ratio=0.2
            df["bonus_ratio"] = pd.to_numeric(df["送股"], errors="coerce").fillna(0.0) / 10.0
            df["transfer_ratio"] = pd.to_numeric(df["转增"], errors="coerce").fillna(0.0) / 10.0
            # 派息：原始值为每10股派多少元，转为每股
            df["cash_dividend"] = pd.to_numeric(df["派息"], errors="coerce").fillna(0.0) / 10.0
            result[code] = df[["date", "cash_dividend", "bonus_ratio", "transfer_ratio"]]
            print(f"  ✓ {code} 分红数据获取完成 ({len(df)} 条)")
        except Exception as e:
            print(f"  ⚠ {code} 分红数据获取失败: {e}，默认为无分红")
            result[code] = pd.DataFrame(columns=["date", "cash_dividend", "bonus_ratio", "transfer_ratio"])

    return result


def fetch_trade_calendar(start: str, end: str) -> set[date]:
    """
    获取交易日历，返回 set[date]，便于快速判断某日是否为交易日。
    """
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")
    try:
        df = _retry(ak.tool_trade_date_hist_sina)
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        trade_dates = set(df["trade_date"])
        # 截取区间内交易日
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
        trade_dates = {d for d in trade_dates if s <= d <= e}
        print(f"  ✓ 交易日历获取完成 ({len(trade_dates)} 个交易日)")
        return trade_dates
    except Exception as e:
        print(f"  ✗ 交易日历获取失败: {e}")
        raise


def fetch_benchmark(index_code: str, start: str, end: str) -> pd.DataFrame:
    """
    获取基准指数日线数据（如沪深 300）。
    """
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")
    try:
        df = _retry(ak.stock_zh_index_daily, symbol=f"sh{index_code}")
        if df is None or df.empty:
            # 尝试 sz 前缀
            df = _retry(ak.stock_zh_index_daily, symbol=f"sz{index_code}")
        df = df.rename(columns={"date": "date", "close": "close"})
        # 兼容不同列名
        date_col = [c for c in df.columns if "date" in c.lower() or "日期" in c][0]
        close_col = [c for c in df.columns if "close" in c.lower() or "收盘" in c][0]
        df = df.rename(columns={date_col: "date", close_col: "close"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
        df = df[(df["date"] >= s) & (df["date"] <= e)]
        df = df.sort_values("date").reset_index(drop=True)
        print(f"  ✓ 基准指数 {index_code} 获取完成 ({len(df)} 条)")
        return df[["date", "close"]]
    except Exception as e:
        print(f"  ✗ 基准指数获取失败: {e}，将跳过基准对比")
        return pd.DataFrame(columns=["date", "close"])
