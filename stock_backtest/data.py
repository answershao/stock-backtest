"""
数据获取、标准化与回测输入装配。
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Set

import pandas as pd

from stock_backtest import config as cfg
from stock_backtest.models import BacktestInputs, MarketContext

EMPTY_DIVIDEND_FRAME = pd.DataFrame(columns=["date", "cash_dividend", "bonus_ratio", "transfer_ratio"])


def as_ratio(series):
    numeric = pd.to_numeric(series, errors="coerce")
    mask = numeric.abs() > 1.5
    numeric.loc[mask] = numeric.loc[mask] / 100.0
    return numeric


def normalize_quote_frame(df):
    if df is None or df.empty:
        return pd.DataFrame()
    data = df.rename(columns={"trade_date": "date"}).copy()
    if "date" not in data.columns:
        return pd.DataFrame()
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.date
    for col in ("open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"):
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["date", "close"])
    if data.empty:
        return pd.DataFrame()
    return data.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)


def normalize_dividend_frame(df):
    if df is None or df.empty:
        return EMPTY_DIVIDEND_FRAME.copy()
    data = df.copy()
    if {"date", "cash_dividend", "bonus_ratio", "transfer_ratio"}.issubset(data.columns):
        data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.date
        data["cash_dividend"] = pd.to_numeric(data["cash_dividend"], errors="coerce").fillna(0.0)
        data["bonus_ratio"] = pd.to_numeric(data["bonus_ratio"], errors="coerce").fillna(0.0)
        data["transfer_ratio"] = pd.to_numeric(data["transfer_ratio"], errors="coerce").fillna(0.0)
        data = data.dropna(subset=["date"])
        return data[["date", "cash_dividend", "bonus_ratio", "transfer_ratio"]]
    if "div_proc" in data.columns:
        data = data[data["div_proc"].isin(["实施", "实施方案", "完成"])]
    if "ex_date" not in data.columns:
        return EMPTY_DIVIDEND_FRAME.copy()
    data["date"] = pd.to_datetime(data["ex_date"], errors="coerce").dt.date
    data["cash_dividend"] = pd.to_numeric(data.get("cash_div_tax"), errors="coerce").fillna(0.0)
    data["bonus_ratio"] = pd.to_numeric(data.get("stk_div"), errors="coerce").fillna(0.0)
    data["transfer_ratio"] = pd.to_numeric(data.get("stk_bo_rate"), errors="coerce").fillna(0.0)
    data = data.dropna(subset=["date"])
    return data[["date", "cash_dividend", "bonus_ratio", "transfer_ratio"]]


def cache_root() -> Path:
    return Path(cfg.DATA_SOURCE.market_cache_dir)


def quote_cache_dir() -> Path:
    adj = get_quote_adjustment()
    return cache_root() / f"quotes_{adj}"


def dividend_cache_dir() -> Path:
    return cache_root() / "dividends"


def benchmark_cache_dir() -> Path:
    return cache_root() / "benchmark"


def fundamentals_cache_dir() -> Path:
    return cache_root() / "fundamentals"


def trade_calendar_cache_path() -> Path:
    return cache_root() / "trade_calendar.csv"


def ensure_cache_dirs() -> None:
    quote_cache_dir().mkdir(parents=True, exist_ok=True)
    dividend_cache_dir().mkdir(parents=True, exist_ok=True)
    benchmark_cache_dir().mkdir(parents=True, exist_ok=True)
    fundamentals_cache_dir().mkdir(parents=True, exist_ok=True)


def quote_cache_path(code: str) -> Path:
    return quote_cache_dir() / f"{code}.csv"


def dividend_cache_path(code: str) -> Path:
    return dividend_cache_dir() / f"{code}.csv"


def benchmark_cache_path(index_code: str) -> Path:
    return benchmark_cache_dir() / f"{index_code}.csv"


def fundamentals_cache_path() -> Path:
    return fundamentals_cache_dir() / "research_fundamentals.csv"


def today_ts() -> str:
    return date.today().strftime("%Y-%m-%d")


def get_quote_adjustment() -> str:
    adj = str(getattr(cfg.DATA_SOURCE, "market_cache_quote_adjustment", "hfq")).strip().lower()
    if adj not in {"hfq", "qfq", "none"}:
        raise ValueError("market_cache_quote_adjustment 仅支持 hfq/qfq/none，当前值: %s" % adj)
    return adj


def iter_quote_adjustments() -> list[Optional[str]]:
    primary = get_quote_adjustment()
    return [None] if primary == "none" else [primary]


def save_quote_cache(code: str, df: pd.DataFrame) -> None:
    ensure_cache_dirs()
    df.sort_values("date").drop_duplicates(subset=["date"], keep="last").to_csv(quote_cache_path(code), index=False)


def save_dividend_cache(code: str, df: pd.DataFrame) -> None:
    ensure_cache_dirs()
    df.sort_values("date").drop_duplicates(subset=["date"], keep="last").to_csv(dividend_cache_path(code), index=False)


def save_trade_calendar_cache(trade_dates: Set[date]) -> None:
    ensure_cache_dirs()
    pd.DataFrame({"cal_date": sorted(trade_dates)}).to_csv(trade_calendar_cache_path(), index=False)


def save_benchmark_cache(index_code: str, df: pd.DataFrame) -> None:
    ensure_cache_dirs()
    df.sort_values("date").drop_duplicates(subset=["date"], keep="last").to_csv(benchmark_cache_path(index_code), index=False)


def save_fundamentals_cache(df: pd.DataFrame) -> None:
    ensure_cache_dirs()
    df.sort_values(["code", "date"]).drop_duplicates(subset=["code", "date"], keep="last").to_csv(
        fundamentals_cache_path(), index=False
    )


def load_quote_cache(code: str) -> pd.DataFrame:
    path = quote_cache_path(code)
    if not path.exists():
        return pd.DataFrame()
    return normalize_quote_frame(pd.read_csv(path))


def load_dividend_cache(code: str) -> pd.DataFrame:
    path = dividend_cache_path(code)
    if not path.exists():
        return EMPTY_DIVIDEND_FRAME.copy()
    return normalize_dividend_frame(pd.read_csv(path))


def load_trade_calendar_cache() -> Set[date]:
    path = trade_calendar_cache_path()
    if not path.exists():
        return set()
    return normalize_trade_calendar(pd.read_csv(path))


def load_benchmark_cache(index_code: str) -> pd.DataFrame:
    path = benchmark_cache_path(index_code)
    if not path.exists():
        return pd.DataFrame(columns=["date", "close"])
    return normalize_benchmark_frame(pd.read_csv(path))


def load_fundamentals_cache() -> pd.DataFrame:
    path = fundamentals_cache_path()
    if not path.exists():
        return pd.DataFrame()
    return standardize_fundamentals(pd.read_csv(path, dtype={"code": str}))


def filter_quote_range(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    return df[(df["date"] >= start_date) & (df["date"] <= end_date)].reset_index(drop=True)


def covers_date_range(df: pd.DataFrame, start: str, end: str) -> bool:
    if df is None or df.empty or "date" not in df.columns:
        return False
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    return df["date"].min() <= start_date and df["date"].max() >= end_date


def filter_dividend_range(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df is None or df.empty:
        return EMPTY_DIVIDEND_FRAME.copy()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    return df[(df["date"] >= start_date) & (df["date"] <= end_date)].reset_index(drop=True)


def filter_fundamentals_range(df: pd.DataFrame, symbols: list[str], start: str, end: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    return df[
        df["code"].astype(str).isin(symbols)
        & (df["date"] >= start_date)
        & (df["date"] <= end_date)
    ].sort_values(["code", "date"]).reset_index(drop=True)


def merge_quote_frames(old_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    frames = [df for df in (old_df, new_df) if df is not None and not df.empty]
    if not frames:
        return pd.DataFrame()
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )


def merge_dividend_frames(old_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    frames = [df for df in (old_df, new_df) if df is not None and not df.empty]
    if not frames:
        return EMPTY_DIVIDEND_FRAME.copy()
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )


def merge_trade_dates(old_dates: Set[date], new_dates: Set[date]) -> Set[date]:
    return set(old_dates) | set(new_dates)


def merge_benchmark_frames(old_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    frames = [df for df in (old_df, new_df) if df is not None and not df.empty]
    if not frames:
        return pd.DataFrame(columns=["date", "close"])
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )


def normalize_trade_calendar(df):
    if df is None or df.empty:
        raise RuntimeError("交易日历获取失败")
    data = df.copy()
    data["cal_date"] = pd.to_datetime(data["cal_date"]).dt.date
    return set(data["cal_date"])


def normalize_benchmark_frame(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "close"])
    data = df.rename(columns={"trade_date": "date"}).copy()
    data["date"] = pd.to_datetime(data["date"]).dt.date
    data = data.sort_values("date").reset_index(drop=True)
    return data[["date", "close"]]


def merge_research_fundamentals(daily_basic, fina, code, industry, listing_date):
    if daily_basic is None or daily_basic.empty:
        return pd.DataFrame()

    base = daily_basic.rename(columns={"trade_date": "date"}).copy()
    base["date"] = pd.to_datetime(base["date"])
    base = base.sort_values("date")

    if fina is not None and not fina.empty:
        fina_data = fina.rename(columns={"end_date": "date", "netprofit_yoy": "net_profit_growth"}).copy()
        fina_data["date"] = pd.to_datetime(fina_data["date"])
        fina_data = fina_data.sort_values("date")
        merged = pd.merge_asof(
            base,
            fina_data[["date", "roe", "net_profit_growth"]],
            on="date",
            direction="backward",
        )
    else:
        merged = base.copy()
        merged["roe"] = pd.NA
        merged["net_profit_growth"] = pd.NA

    merged["code"] = code
    merged["industry"] = industry
    merged["listing_date"] = listing_date
    merged["date"] = merged["date"].dt.date
    return merged[["date", "code", "pe_ttm", "pb", "roe", "industry", "net_profit_growth", "listing_date"]]


def standardize_fundamentals(df):
    rename_map = {
        "trade_date": "date",
        "datetime": "date",
        "ticker": "code",
        "symbol": "code",
        "证券代码": "code",
        "股票代码": "code",
        "pe": "pe_ttm",
        "PE_TTM": "pe_ttm",
        "pe_ttm_m": "pe_ttm",
        "pb_lf": "pb",
        "PB": "pb",
        "ROE": "roe",
        "industry_name": "industry",
        "申万一级行业": "industry",
        "净利润增速": "net_profit_growth",
        "profit_growth": "net_profit_growth",
        "g": "g_forward_3y",
        "growth_3y": "g_forward_3y",
        "forward_g": "g_forward_3y",
        "listingDate": "listing_date",
        "上市日期": "listing_date",
    }
    data = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}).copy()

    required = {"date", "code", "pe_ttm", "roe", "industry", "net_profit_growth"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError("基本面数据缺少必需字段: %s" % sorted(missing))

    data["date"] = pd.to_datetime(data["date"]).dt.date
    data["code"] = data["code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna(data["code"].astype(str))

    for col in ("roe", "net_profit_growth", "g_forward_3y", "net_profit_growth_3y_cagr", "net_profit_growth_2y_cagr"):
        if col in data.columns:
            data[col] = as_ratio(data[col])

    for col in ("pe_ttm", "pb"):
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

    if "listing_date" in data.columns:
        data["listing_date"] = pd.to_datetime(data["listing_date"], errors="coerce").dt.date

    if "is_st" in data.columns:
        data["is_st"] = data["is_st"].fillna(False).astype(bool)

    data["industry"] = data["industry"].astype(str).str.strip()
    return data.sort_values(["code", "date"]).reset_index(drop=True)


def load_fundamentals_csv_frame(path):
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(
            "未找到基本面数据文件: %s. 请准备包含 date/code/pe_ttm/roe/industry/net_profit_growth 的 CSV。"
            % csv_path
        )
    df = pd.read_csv(csv_path, dtype={"code": str})
    if df.empty:
        raise ValueError("基本面数据为空: %s" % csv_path)
    return df


def require_tushare():
    try:
        import tushare as ts
        from tushare.pro import client as ts_client
    except ImportError as exc:
        raise ImportError("未安装 tushare。请先执行: pip install tushare") from exc

    ts_client.DataApi._DataApi__http_url = cfg.DATA_SOURCE.tushare_http_url
    pro = ts.pro_api(cfg.DATA_SOURCE.tushare_token)
    return ts, pro


def throttle():
    time.sleep(cfg.DATA_SOURCE.tushare_rate_limit_seconds)


def to_ts_code(code, asset="E"):
    code = str(code).strip()
    if code.endswith((".SH", ".SZ")):
        return code.upper()
    if asset == "I":
        # Tushare 指数代码不能按股票规则推断；常见宽基如 000300/000905/000852 都是 .SH，
        # 深证系列如 399001/399300 才是 .SZ。
        suffix = ".SZ" if code.startswith("399") else ".SH"
        return "%s%s" % (code, suffix)
    suffix = ".SH" if code.startswith(("5", "6", "9")) else ".SZ"
    return "%s%s" % (code, suffix)


def date_to_ts(value):
    return value.replace("-", "")


def fetch_trade_calendar_raw(start, end):
    _, pro = require_tushare()
    df = pro.trade_cal(exchange="", start_date=date_to_ts(start), end_date=date_to_ts(end), is_open="1")
    throttle()
    return df


def fetch_daily_quotes_raw(symbols, start, end):
    ts, pro = require_tushare()
    result = {}
    start_fmt = date_to_ts(start)
    end_fmt = date_to_ts(end)
    for code in symbols:
        used_adj = None
        df = pd.DataFrame()
        for adj in iter_quote_adjustments():
            kwargs = {
                "api": pro,
                "ts_code": to_ts_code(code),
                "asset": "E",
                "start_date": start_fmt,
                "end_date": end_fmt,
            }
            if adj is not None:
                kwargs["adj"] = adj
            candidate = ts.pro_bar(**kwargs)
            throttle()
            normalized = normalize_quote_frame(candidate)
            if not normalized.empty:
                df = candidate
                used_adj = adj
                break
        result[code] = {"df": df, "adj": used_adj}
    return result


def fetch_dividends_raw(symbols):
    _, pro = require_tushare()
    result = {}
    for code in symbols:
        df = pro.dividend(ts_code=to_ts_code(code))
        throttle()
        result[code] = df
    return result


def fetch_benchmark_raw(index_code, start, end):
    ts, pro = require_tushare()
    ts_code = to_ts_code(index_code, asset="I")
    df = pro.index_daily(ts_code=ts_code, start_date=date_to_ts(start), end_date=date_to_ts(end))
    throttle()
    if df is None or df.empty:
        df = ts.pro_bar(api=pro, ts_code=ts_code, asset="I", start_date=date_to_ts(start), end_date=date_to_ts(end))
        throttle()
    return df


def fetch_stock_basic_raw():
    _, pro = require_tushare()
    df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,industry,list_date")
    throttle()
    return df


def fetch_daily_basic_raw(code, start, end):
    _, pro = require_tushare()
    df = pro.daily_basic(
        ts_code=to_ts_code(code),
        start_date=date_to_ts(start),
        end_date=date_to_ts(end),
        fields="ts_code,trade_date,pe_ttm,pb",
    )
    throttle()
    return df


def fetch_fina_indicator_raw(code, start, end):
    _, pro = require_tushare()
    df = pro.fina_indicator(
        ts_code=to_ts_code(code),
        start_date=date_to_ts(start),
        end_date=date_to_ts(end),
        fields="ts_code,end_date,roe,netprofit_yoy",
    )
    throttle()
    return df


def fetch_daily_quotes(symbols, start, end):
    raw_result = fetch_daily_quotes_raw(symbols, start, end)
    result = {}
    for code, payload in raw_result.items():
        try:
            raw_df = payload.get("df", pd.DataFrame())
            used_adj = payload.get("adj")
            df = normalize_quote_frame(raw_df)
            if df.empty:
                print("  %s 无日线数据，跳过" % code)
                continue
            result[code] = df
            adj_label = used_adj or "none"
            print("  %s 日线数据获取完成 (%s 条, adj=%s)" % (code, len(df), adj_label))
        except Exception as exc:
            print("  %s 日线数据获取失败: %s" % (code, exc))
    return result


def fetch_dividends(symbols):
    raw_result = fetch_dividends_raw(symbols)
    result = {}
    for code, raw_df in raw_result.items():
        try:
            df = normalize_dividend_frame(raw_df)
            result[code] = df if not df.empty else EMPTY_DIVIDEND_FRAME.copy()
            print("  %s 分红数据获取完成 (%s 条)" % (code, len(result[code])))
        except Exception as exc:
            print("  %s 分红数据获取失败: %s，默认为无分红" % (code, exc))
            result[code] = EMPTY_DIVIDEND_FRAME.copy()
    return result


def refresh_quote_cache_for_code(code: str, force_full: bool = False) -> pd.DataFrame:
    cached = load_quote_cache(code)
    if force_full or cached.empty:
        start = cfg.DATA_SOURCE.market_cache_start_date
    else:
        start = (cached["date"].max() + timedelta(days=1)).isoformat()

    end = today_ts()
    if not force_full and start > end:
        return cached

    fresh = fetch_daily_quotes([code], start, end).get(code, pd.DataFrame())
    merged = merge_quote_frames(pd.DataFrame() if force_full else cached, fresh)
    if not merged.empty:
        save_quote_cache(code, merged)
    return merged


def ensure_quote_cache_range(code: str, start: str, end: str) -> pd.DataFrame:
    cached = load_quote_cache(code)
    if cached.empty:
        fresh = fetch_daily_quotes([code], start, end).get(code, pd.DataFrame())
        merged = merge_quote_frames(cached, fresh)
    else:
        frames = [cached]
        cached_start = cached["date"].min()
        cached_end = cached["date"].max()
        request_start = date.fromisoformat(start)
        request_end = date.fromisoformat(end)
        if request_start < cached_start:
            head = fetch_daily_quotes([code], start, (cached_start - timedelta(days=1)).isoformat()).get(code, pd.DataFrame())
            frames.append(head)
        if request_end > cached_end:
            tail = fetch_daily_quotes([code], (cached_end + timedelta(days=1)).isoformat(), end).get(code, pd.DataFrame())
            frames.append(tail)
        merged = merge_quote_frames(pd.DataFrame(), pd.concat([df for df in frames if df is not None and not df.empty], ignore_index=True) if any(not df.empty for df in frames) else pd.DataFrame())
    if not merged.empty:
        save_quote_cache(code, merged)
    return merged


def ensure_benchmark_cache_range(index_code: str, start: str, end: str) -> pd.DataFrame:
    cached = load_benchmark_cache(index_code)
    if cached.empty:
        fresh = fetch_benchmark(index_code, start, end)
        merged = merge_benchmark_frames(cached, fresh)
    else:
        frames = [cached]
        cached_start = cached["date"].min()
        cached_end = cached["date"].max()
        request_start = date.fromisoformat(start)
        request_end = date.fromisoformat(end)
        if request_start < cached_start:
            head = fetch_benchmark(index_code, start, (cached_start - timedelta(days=1)).isoformat())
            frames.append(head)
        if request_end > cached_end:
            tail = fetch_benchmark(index_code, (cached_end + timedelta(days=1)).isoformat(), end)
            frames.append(tail)
        merged = merge_benchmark_frames(
            pd.DataFrame(columns=["date", "close"]),
            pd.concat([df for df in frames if df is not None and not df.empty], ignore_index=True)
            if any(not df.empty for df in frames)
            else pd.DataFrame(columns=["date", "close"]),
        )
    if not merged.empty:
        save_benchmark_cache(index_code, merged)
    return merged


def refresh_dividend_cache_for_code(code: str, force_full: bool = False) -> pd.DataFrame:
    if force_full:
        cached = EMPTY_DIVIDEND_FRAME.copy()
    else:
        cached = load_dividend_cache(code)
    fresh = fetch_dividends([code]).get(code, EMPTY_DIVIDEND_FRAME.copy())
    merged = merge_dividend_frames(cached, fresh)
    save_dividend_cache(code, merged)
    return merged


def refresh_trade_calendar_cache(start: str, end: str, force_full: bool = False) -> Set[date]:
    cached = set() if force_full else load_trade_calendar_cache()
    fresh = fetch_trade_calendar(start, end)
    merged = merge_trade_dates(cached, fresh)
    save_trade_calendar_cache(merged)
    return merged


def refresh_benchmark_cache(index_code: str, force_full: bool = False) -> pd.DataFrame:
    cached = pd.DataFrame(columns=["date", "close"]) if force_full else load_benchmark_cache(index_code)
    start = cfg.DATA_SOURCE.market_cache_start_date if force_full or cached.empty else (cached["date"].max() + timedelta(days=1)).isoformat()
    end = today_ts()
    if not force_full and start > end:
        return cached
    fresh = fetch_benchmark(index_code, start, end)
    merged = merge_benchmark_frames(pd.DataFrame(columns=["date", "close"]) if force_full else cached, fresh)
    if not merged.empty:
        save_benchmark_cache(index_code, merged)
    return merged


def prefetch_universe_market_cache(force_full: bool = False) -> None:
    ensure_cache_dirs()
    symbols = cfg.UNIVERSE.stock_codes
    cache_start = cfg.DATA_SOURCE.market_cache_start_date
    cache_end = today_ts()
    print("开始预热股票池缓存...")
    print("  股票数量: %s" % len(symbols))
    print("  预热交易日历缓存...")
    refresh_trade_calendar_cache(cache_start, cache_end, force_full=force_full)
    print("  预热基准指数缓存...")
    if force_full:
        refresh_benchmark_cache(cfg.BACKTEST.benchmark_index, force_full=True)
    else:
        ensure_benchmark_cache_range(cfg.BACKTEST.benchmark_index, cache_start, cache_end)
    for code in symbols:
        print("  预热 %s 日线缓存..." % code)
        if force_full:
            refresh_quote_cache_for_code(code, force_full=True)
        else:
            ensure_quote_cache_range(code, cache_start, cache_end)
        print("  预热 %s 分红缓存..." % code)
        refresh_dividend_cache_for_code(code, force_full=force_full)
    if cfg.is_value_portfolio_mode():
        print("  预热研究版基本面缓存...")
        if force_full and fundamentals_cache_path().exists():
            fundamentals_cache_path().unlink()
        ensure_fundamentals_cache_range(symbols, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)
    print("股票池缓存预热完成，目录: %s" % cache_root().resolve())


def load_cached_quotes(symbols, start, end, auto_fetch_missing: bool = True):
    ensure_cache_dirs()
    result = {}
    for code in symbols:
        cached = load_quote_cache(code)
        df = filter_quote_range(cached, start, end)
        if (df.empty or not covers_date_range(cached, start, end)) and auto_fetch_missing:
            print("  %s 本地缓存区间不完整，开始补拉日线..." % code)
            ensure_quote_cache_range(code, start, end)
            df = filter_quote_range(load_quote_cache(code), start, end)
        if df.empty:
            print("  %s 回测区间内无日线数据，跳过" % code)
            continue
        result[code] = df
    return result


def load_cached_dividends(symbols, start: str, end: str, auto_fetch_missing: bool = True):
    ensure_cache_dirs()
    result = {}
    for code in symbols:
        path = dividend_cache_path(code)
        if not path.exists() and auto_fetch_missing:
            print("  %s 本地缓存缺失，开始补拉分红..." % code)
            refresh_dividend_cache_for_code(code, force_full=False)
        df = filter_dividend_range(load_dividend_cache(code), start, end)
        result[code] = df if not df.empty else EMPTY_DIVIDEND_FRAME.copy()
    return result


def load_cached_trade_calendar(start: str, end: str, auto_fetch_missing: bool = True) -> Set[date]:
    ensure_cache_dirs()
    cached = load_trade_calendar_cache()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    filtered = {d for d in cached if start_date <= d <= end_date}
    if (filtered and min(filtered) <= start_date and max(filtered) >= end_date) or not auto_fetch_missing:
        print("  交易日历缓存加载完成 (%s 个交易日)" % len(filtered))
        return filtered
    print("  交易日历本地缓存缺失，开始补拉...")
    refresh_trade_calendar_cache(start, end, force_full=False)
    cached = load_trade_calendar_cache()
    filtered = {d for d in cached if start_date <= d <= end_date}
    print("  交易日历缓存加载完成 (%s 个交易日)" % len(filtered))
    return filtered


def load_cached_benchmark(index_code: str, start: str, end: str, auto_fetch_missing: bool = True) -> pd.DataFrame:
    ensure_cache_dirs()
    cached = load_benchmark_cache(index_code)
    filtered = filter_quote_range(cached, start, end)[["date", "close"]] if not cached.empty else pd.DataFrame(columns=["date", "close"])
    if (covers_date_range(cached, start, end) and not filtered.empty) or not auto_fetch_missing:
        print("  基准指数 %s 缓存加载完成 (%s 条): %s" % (index_code, len(filtered), benchmark_cache_path(index_code)))
        return filtered
    print("  基准指数 %s 本地缓存缺失，开始补拉: %s" % (index_code, benchmark_cache_path(index_code)))
    refresh_benchmark_cache(index_code, force_full=False)
    cached = load_benchmark_cache(index_code)
    filtered = filter_quote_range(cached, start, end)[["date", "close"]] if not cached.empty else pd.DataFrame(columns=["date", "close"])
    print("  基准指数 %s 缓存加载完成 (%s 条): %s" % (index_code, len(filtered), benchmark_cache_path(index_code)))
    return filtered


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


def fetch_research_fundamentals(
    symbols,
    start,
    end,
    existing_cache: Optional[pd.DataFrame] = None,
    incremental_persist: bool = False,
):
    stock_basic = fetch_stock_basic_raw()
    if stock_basic is None or stock_basic.empty:
        raise RuntimeError("stock_basic 获取失败")

    stock_basic = stock_basic.copy()
    stock_basic["code"] = stock_basic["symbol"].astype(str)
    stock_basic["listing_date"] = pd.to_datetime(stock_basic["list_date"], errors="coerce").dt.date
    stock_basic = stock_basic[stock_basic["code"].isin(symbols)].copy()

    frames = []
    running_cache = existing_cache.copy() if existing_cache is not None and not existing_cache.empty else pd.DataFrame()
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
            if incremental_persist:
                running_cache = merge_fundamentals_frames(running_cache, merged)
                save_fundamentals_cache(running_cache)
            print("  %s 基本面数据获取完成 (%s 条)" % (code, len(merged)))
        except Exception as exc:
            print("  %s 基本面数据获取失败: %s" % (code, exc))

    if not frames:
        raise RuntimeError("未获取到任何研究版基本面数据")
    return standardize_fundamentals(pd.concat(frames, ignore_index=True))


def load_fundamentals_csv(path):
    return standardize_fundamentals(load_fundamentals_csv_frame(Path(path)))


def merge_fundamentals_frames(old_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    frames = [df for df in (old_df, new_df) if df is not None and not df.empty]
    if not frames:
        return pd.DataFrame()
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(["code", "date"])
        .drop_duplicates(subset=["code", "date"], keep="last")
        .reset_index(drop=True)
    )


def fundamentals_cache_covers(df: pd.DataFrame, symbols: list[str], start: str, end: str) -> bool:
    if df is None or df.empty:
        return False
    trade_dates = load_trade_calendar_cache()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    expected_start = next_trade_date(start_date, trade_dates) if trade_dates else start_date
    expected_end = previous_trade_date(end_date, trade_dates) if trade_dates else end_date
    if expected_start is None or expected_end is None:
        expected_start = start_date
        expected_end = end_date
    for code in symbols:
        code_df = df[df["code"].astype(str) == str(code)]
        if code_df.empty:
            return False
        if code_df["date"].min() > expected_start or code_df["date"].max() < expected_end:
            return False
    return True


def fundamentals_code_covers(
    df: pd.DataFrame, code: str, expected_start: date, expected_end: date
) -> bool:
    if df is None or df.empty:
        return False
    code_df = df[df["code"].astype(str) == str(code)]
    if code_df.empty:
        return False
    return code_df["date"].min() <= expected_start and code_df["date"].max() >= expected_end


def ensure_fundamentals_cache_range(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    cached = load_fundamentals_cache()
    if fundamentals_cache_covers(cached, symbols, start, end):
        return cached
    trade_dates = load_trade_calendar_cache()
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    expected_start = next_trade_date(start_date, trade_dates) if trade_dates else start_date
    expected_end = previous_trade_date(end_date, trade_dates) if trade_dates else end_date
    if expected_start is None or expected_end is None:
        expected_start = start_date
        expected_end = end_date

    pending_symbols = [
        code for code in symbols if not fundamentals_code_covers(cached, code, expected_start, expected_end)
    ]
    fresh = fetch_research_fundamentals(
        pending_symbols,
        start,
        end,
        existing_cache=cached,
        incremental_persist=True,
    )
    merged = merge_fundamentals_frames(cached, fresh)
    if not merged.empty:
        save_fundamentals_cache(merged)
    return merged


def next_trade_date(target_date: date, trade_dates: Set[date], max_lookahead: int = 30) -> Optional[date]:
    for offset in range(max_lookahead):
        candidate = target_date + timedelta(days=offset)
        if candidate in trade_dates:
            return candidate
    return None


def previous_trade_date(target_date: date, trade_dates: Set[date], max_lookback: int = 30) -> Optional[date]:
    for offset in range(max_lookback):
        candidate = target_date - timedelta(days=offset)
        if candidate in trade_dates:
            return candidate
    return None


def generate_rebalance_dates(start: date, end: date, schedule: list[str], trade_dates: Set[date]) -> list[date]:
    theoretical_dates = []
    for year in range(start.year, end.year + 1):
        for mmdd in schedule:
            month, day = mmdd.split("-")
            theoretical_dates.append(date(year, int(month), int(day)))

    actual_dates = []
    for theoretical_date in sorted(d for d in theoretical_dates if start <= d <= end):
        actual_date = next_trade_date(theoretical_date, trade_dates)
        if actual_date is not None and actual_date <= end:
            actual_dates.append(actual_date)
    return actual_dates


def load_fundamentals_for_mode() -> Optional[pd.DataFrame]:
    if not cfg.is_value_portfolio_mode():
        return None

    csv_path = Path(cfg.DATA_SOURCE.fundamental_data_path)
    if csv_path.exists():
        print(f"使用本地基本面文件: {csv_path}")
        return load_fundamentals_csv(csv_path)

    cache_path = fundamentals_cache_path()
    cached = load_fundamentals_cache()
    if fundamentals_cache_covers(cached, cfg.UNIVERSE.stock_codes, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date):
        print(f"使用研究版基本面缓存: {cache_path}")
        return filter_fundamentals_range(
            cached,
            cfg.UNIVERSE.stock_codes,
            cfg.BACKTEST.start_date,
            cfg.BACKTEST.end_date,
        )

    print(f"研究版基本面缓存不足，开始补拉并写入: {cache_path}")
    cached = ensure_fundamentals_cache_range(
        cfg.UNIVERSE.stock_codes,
        cfg.BACKTEST.start_date,
        cfg.BACKTEST.end_date,
    )
    return filter_fundamentals_range(
        cached,
        cfg.UNIVERSE.stock_codes,
        cfg.BACKTEST.start_date,
        cfg.BACKTEST.end_date,
    )


def load_backtest_inputs() -> BacktestInputs:
    print("开始按需加载交易日历缓存...")
    trade_dates = load_cached_trade_calendar(cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)

    print("开始按需加载股票行情缓存...")
    quotes = load_cached_quotes(cfg.UNIVERSE.stock_codes, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)

    print("开始按需加载分红缓存...")
    dividends = load_cached_dividends(cfg.UNIVERSE.stock_codes, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)

    print("开始按需加载基准指数缓存...")
    benchmark = load_cached_benchmark(cfg.BACKTEST.benchmark_index, cfg.BACKTEST.start_date, cfg.BACKTEST.end_date)

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
