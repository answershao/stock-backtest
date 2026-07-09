"""
数据获取模块 — 基于 Tushare
- 日线行情（可配置复权方式）
- 历史分红送配
- 交易日历
- 基准指数行情
"""

from __future__ import annotations

import os
import random
import time
from datetime import date
from pathlib import Path

import pandas as pd

import config as cfg

try:
    import tushare as ts
    from tushare.pro import client as _ts_client
except ImportError as exc:
    raise ImportError("请先安装 tushare: pip install tushare") from exc


def _retry(func, *args, max_retries=3, base_delay=3, **kwargs):
    """带随机退避的重试机制，用于应对 API 限流。"""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if isinstance(e, TypeError):
                raise
            if attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt) + random.uniform(0, 2)
                print(f"    ⏳ 请求失败 ({e.__class__.__name__}), {wait:.1f}s 后重试...")
                time.sleep(wait)
            else:
                raise


def _require_token() -> str:
    """读取并校验 Tushare Token。"""
    token = cfg.TUSHARE_TOKEN.strip()
    if not token:
        raise ValueError("未配置 TUSHARE_TOKEN，无法从 Tushare 拉取数据")
    return token


def _configure_proxy() -> None:
    """按配置切换 Tushare 请求地址代理。"""
    proxy_url = cfg.TUSHARE_PROXY_URL.strip()
    if proxy_url:
        _ts_client.DataApi._DataApi__http_url = proxy_url


def _to_ts_code(code: str) -> str:
    """将 6 位股票代码转换为 Tushare ts_code。"""
    if code.endswith(".SH") or code.endswith(".SZ") or code.endswith(".BJ"):
        return code
    if code.startswith(("600", "601", "603", "605", "688", "900")):
        return f"{code}.SH"
    if code.startswith(("000", "001", "002", "003", "300", "301", "200")):
        return f"{code}.SZ"
    if code.startswith(("430", "830", "831", "832", "833", "834", "835", "836", "837", "838", "839", "870", "871", "872", "873", "874", "875", "876", "877", "878", "879")):
        return f"{code}.BJ"
    raise ValueError(f"无法识别股票代码后缀: {code}")


def _normalize_trade_date(value) -> date:
    """兼容 YYYYMMDD 和日期对象。"""
    if isinstance(value, date):
        return value
    return pd.to_datetime(str(value)).date()


def _get_pro_client():
    """初始化 Tushare Pro 客户端。"""
    _configure_proxy()
    token = _require_token()
    ts.set_token(token)
    return ts.pro_api(token)


def _fetch_pro_bar_compatible(pro, ts_code: str, start_fmt: str, end_fmt: str) -> pd.DataFrame | None:
    """兼容不同 tushare 版本的 pro_bar 参数签名。"""
    adj = cfg.PRICE_ADJ if cfg.PRICE_ADJ else None
    attempts = [
        {
            "ts_code": ts_code,
            "start_date": start_fmt,
            "end_date": end_fmt,
            "asset": "E",
            "pro_api": pro,
        },
        {
            "ts_code": ts_code,
            "start_date": start_fmt,
            "end_date": end_fmt,
            "asset": "E",
            "api": pro,
        },
        {
            "ts_code": ts_code,
            "start_date": start_fmt,
            "end_date": end_fmt,
            "pro_api": pro,
        },
        {
            "ts_code": ts_code,
            "start_date": start_fmt,
            "end_date": end_fmt,
            "api": pro,
        },
        {
            "ts_code": ts_code,
            "start_date": start_fmt,
            "end_date": end_fmt,
        },
    ]

    if adj:
        for kwargs in attempts:
            kwargs["adj"] = adj

    last_type_error = None
    for kwargs in attempts:
        try:
            return _retry(ts.pro_bar, **kwargs)
        except TypeError as exc:
            last_type_error = exc
            continue
    if last_type_error is not None:
        raise last_type_error
    return None


def _cache_enabled() -> bool:
    """是否启用本地缓存。"""
    env_value = os.getenv("CACHE_ENABLED", "").strip().lower()
    if env_value:
        return env_value in {"1", "true", "yes", "on"}
    return bool(cfg.CACHE_ENABLED)


def _cache_force_refresh() -> bool:
    """是否强制刷新缓存。"""
    env_value = os.getenv("CACHE_FORCE_REFRESH", "").strip().lower()
    if env_value:
        return env_value in {"1", "true", "yes", "on"}
    return bool(cfg.CACHE_FORCE_REFRESH)


def _cache_root() -> Path:
    """返回缓存根目录。"""
    root = Path(cfg.CACHE_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _price_adj_suffix() -> str:
    """返回行情缓存文件的复权后缀。"""
    return cfg.PRICE_ADJ if cfg.PRICE_ADJ else "raw"


def _read_cache(path: Path, date_cols: list[str] | None = None) -> pd.DataFrame | None:
    """读取缓存文件。"""
    if not _cache_enabled() or _cache_force_refresh() or not path.exists():
        return None
    df = pd.read_csv(path)
    if date_cols:
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col]).dt.date
    return df


def _write_cache(df: pd.DataFrame, path: Path) -> None:
    """写入缓存文件。"""
    if not _cache_enabled():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def fetch_daily_quotes(symbols: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """
    获取每只股票的日线数据。

    返回
    ----
    dict[str, DataFrame]    按股票代码索引的 DataFrame，列含:
        date, open, high, low, close, volume, amount, turnover
    """
    pro = None
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")
    cache_dir = _cache_root() / "quotes"
    adj_label = _price_adj_suffix()

    result = {}
    for i, code in enumerate(symbols):
        try:
            cache_path = cache_dir / f"{code}_{start_fmt}_{end_fmt}_{adj_label}.csv"
            cached = _read_cache(cache_path, ["date"])
            if cached is not None:
                result[code] = cached
                print(f"  ✓ {code} 日线数据读取缓存 ({len(cached)} 条)")
                continue
            if i > 0:
                time.sleep(random.uniform(0.3, 0.8))
            if pro is None:
                pro = _get_pro_client()
            ts_code = _to_ts_code(code)
            df = _fetch_pro_bar_compatible(pro, ts_code, start_fmt, end_fmt)
            if df is None or df.empty:
                print(f"  ⚠ {code} 无数据，跳过")
                continue
            df = df.rename(
                columns={
                    "trade_date": "date",
                    "vol": "volume",
                    "amount": "amount",
                }
            )
            df["date"] = df["date"].apply(_normalize_trade_date)
            if "turnover_rate" not in df.columns:
                df["turnover_rate"] = pd.NA
            df = df.rename(columns={"turnover_rate": "turnover"})
            keep_cols = ["date", "open", "high", "low", "close", "volume", "amount", "turnover"]
            for col in keep_cols:
                if col not in df.columns:
                    df[col] = pd.NA
            df = df[keep_cols].sort_values("date").reset_index(drop=True)
            result[code] = df
            _write_cache(df, cache_path)
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
    empty = pd.DataFrame(columns=["date", "cash_dividend", "bonus_ratio", "transfer_ratio"])
    pro = None
    cache_dir = _cache_root() / "dividends"

    result = {}
    for i, code in enumerate(symbols):
        try:
            cache_path = cache_dir / f"{code}.csv"
            cached = _read_cache(cache_path, ["date"])
            if cached is not None:
                result[code] = cached
                print(f"  ✓ {code} 分红数据读取缓存 ({len(cached)} 条)")
                continue
            if i > 0:
                time.sleep(random.uniform(0.2, 0.5))
            if pro is None:
                pro = _get_pro_client()
            ts_code = _to_ts_code(code)
            df = _retry(pro.dividend, ts_code=ts_code)
            if df is None or df.empty:
                result[code] = empty.copy()
                _write_cache(result[code], cache_path)
                continue

            df = df.copy()
            if "div_proc" in df.columns:
                implemented_mask = df["div_proc"].astype(str).str.contains("实施|完成", na=False)
                if implemented_mask.any():
                    df = df[implemented_mask]

            ex_date_col = "ex_date" if "ex_date" in df.columns else "imp_ann_date"
            df = df[df[ex_date_col].notna()].copy()
            if df.empty:
                result[code] = empty.copy()
                continue

            df["date"] = df[ex_date_col].apply(_normalize_trade_date)

            stk_bo_rate = pd.to_numeric(df.get("stk_bo_rate", 0.0), errors="coerce").fillna(0.0)
            stk_co_rate = pd.to_numeric(df.get("stk_co_rate", 0.0), errors="coerce").fillna(0.0)
            cash_div_tax = pd.to_numeric(df.get("cash_div_tax", 0.0), errors="coerce").fillna(0.0)

            df["bonus_ratio"] = stk_bo_rate / 10.0
            df["transfer_ratio"] = stk_co_rate / 10.0
            df["cash_dividend"] = cash_div_tax / 10.0

            result[code] = (
                df[["date", "cash_dividend", "bonus_ratio", "transfer_ratio"]]
                .sort_values("date")
                .reset_index(drop=True)
            )
            _write_cache(result[code], cache_path)
            print(f"  ✓ {code} 分红数据获取完成 ({len(result[code])} 条)")
        except Exception as e:
            print(f"  ⚠ {code} 分红数据获取失败: {e}，默认为无分红")
            result[code] = empty.copy()

    return result


def fetch_trade_calendar(start: str, end: str) -> set[date]:
    """
    获取交易日历，返回 set[date]，便于快速判断某日是否为交易日。
    """
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")
    cache_path = _cache_root() / "trade_calendar" / f"{start_fmt}_{end_fmt}.csv"
    try:
        cached = _read_cache(cache_path, ["trade_date"])
        if cached is not None:
            trade_dates = set(cached["trade_date"])
            print(f"  ✓ 交易日历读取缓存 ({len(trade_dates)} 个交易日)")
            return trade_dates
        pro = _get_pro_client()
        df = _retry(
            pro.trade_cal,
            exchange="SSE",
            start_date=start_fmt,
            end_date=end_fmt,
        )
        if df is None or df.empty:
            raise RuntimeError("Tushare trade_cal 返回为空")
        df = df[df["is_open"] == 1].copy()
        df["trade_date"] = df["cal_date"].apply(_normalize_trade_date)
        trade_dates = set(df["trade_date"])
        _write_cache(df[["trade_date"]], cache_path)
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
    cache_path = _cache_root() / "benchmark" / f"{index_code}_{start_fmt}_{end_fmt}.csv"
    try:
        cached = _read_cache(cache_path, ["date"])
        if cached is not None:
            print(f"  ✓ 基准指数 {index_code} 读取缓存 ({len(cached)} 条)")
            return cached
        pro = _get_pro_client()
        ts_code = _to_ts_code(index_code.split(".")[0]) if "." not in index_code else index_code
        df = _retry(
            pro.index_daily,
            ts_code=ts_code,
            start_date=start_fmt,
            end_date=end_fmt,
        )
        if df is None or df.empty:
            raise RuntimeError(f"指数 {index_code} 无数据")
        df = df.rename(columns={"trade_date": "date"})
        df["date"] = df["date"].apply(_normalize_trade_date)
        df = df[["date", "close"]].sort_values("date").reset_index(drop=True)
        _write_cache(df, cache_path)
        print(f"  ✓ 基准指数 {index_code} 获取完成 ({len(df)} 条)")
        return df
    except Exception as e:
        print(f"  ✗ 基准指数获取失败: {e}，将跳过基准对比")
        return pd.DataFrame(columns=["date", "close"])
