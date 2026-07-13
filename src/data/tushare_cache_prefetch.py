from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.data.cache import TushareDataCache
from src.data.tushare_cache_helpers import (
    filter_frame_by_date_range,
    legacy_cache_patterns,
    load_cached_dataset_frame,
    sanitize_cache_key_parts,
    update_incremental_cache,
)
from src.data.tushare_expected_return import fetch_report_rc_from_tushare

FULL_HISTORY_START_DATE = "19900101"


@dataclass(frozen=True)
class TushareCacheArtifacts:
    trading_dates: tuple[pd.Timestamp, ...]
    cache_dir: Path


def fetch_open_trade_dates(pro, start_date: str, end_date: str) -> tuple[pd.Timestamp, ...]:
    cal = pro.trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1")
    if cal is None or cal.empty:
        raise ValueError("Tushare 未返回交易日历。")
    dates = pd.to_datetime(cal["cal_date"].astype(str), format="%Y%m%d", errors="coerce").dropna()
    if dates.empty:
        raise ValueError("交易日历为空。")
    return tuple(sorted(dates.tolist()))


def fetch_open_trade_dates_cached(
    pro,
    *,
    start_date: str,
    end_date: str,
    cache: TushareDataCache | None,
) -> tuple[pd.Timestamp, ...]:
    if cache is None:
        return fetch_open_trade_dates(pro, start_date, end_date)
    frame = load_cached_dataset_frame(
        cache=cache,
        dataset="trade_cal",
        canonical_key_parts=["full", "is_open_1"],
        legacy_glob_patterns=legacy_cache_patterns(dataset="trade_cal", key_parts=["full", "is_open_1"]),
        fallback_fetcher=lambda: cache.load_or_fetch(
            dataset="trade_cal",
            key_parts=[start_date, end_date, "is_open_1"],
            fetcher=lambda: pro.trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1"),
        ),
    )
    if frame.empty:
        raise ValueError("Tushare 未返回交易日历。")
    frame = filter_frame_by_date_range(frame, "cal_date", start_date, end_date)
    dates = pd.to_datetime(frame["cal_date"].astype(str), format="%Y%m%d", errors="coerce").dropna()
    if dates.empty:
        raise ValueError("交易日历为空。")
    return tuple(sorted(dates.tolist()))


def prefetch_tushare_cache(
    pro,
    *,
    stock_pool: list[str],
    cache_dir: str | Path,
    end_date: str | None = None,
    report_rc_start_date: str = FULL_HISTORY_START_DATE,
    refresh_datasets: tuple[str, ...] = (),
) -> TushareCacheArtifacts:
    resolved_end_date = end_date or pd.Timestamp.now().strftime("%Y%m%d")
    cache_root = Path(cache_dir)
    cache = TushareDataCache(cache_root, cache_only=False)
    clear_selected_cache_files(cache_root, stock_pool=stock_pool, datasets=refresh_datasets)
    trading_dates = update_trade_cal_cache(
        pro,
        cache=cache,
        start_date=FULL_HISTORY_START_DATE,
        end_date=resolved_end_date,
    )
    for ts_code in stock_pool:
        update_daily_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=resolved_end_date, trading_dates=trading_dates)
        update_daily_basic_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=resolved_end_date, trading_dates=trading_dates)
        update_report_rc_cache(pro, ts_code, cache=cache, start_date=report_rc_start_date, end_date=resolved_end_date)
        update_fina_indicator_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=resolved_end_date)
        update_dividend_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=resolved_end_date)
    return TushareCacheArtifacts(trading_dates=trading_dates, cache_dir=cache_root)


def clear_tushare_cache_dir(cache_dir: str | Path) -> None:
    path = Path(cache_dir)
    if path.exists():
        for csv_file in path.rglob("*.csv"):
            csv_file.unlink()
    path.mkdir(parents=True, exist_ok=True)


def clear_selected_cache_files(
    cache_root: Path,
    *,
    stock_pool: list[str],
    datasets: tuple[str, ...],
) -> None:
    if not datasets:
        return

    normalized = {item.strip() for item in datasets if item and item.strip()}
    for dataset in normalized:
        if dataset == "trade_cal":
            path = cache_root / dataset / "full__is_open_1.csv"
            if path.exists():
                path.unlink()
            continue

        if dataset == "daily":
            suffix = ["close"]
        elif dataset == "daily_basic":
            suffix = ["pe_ttm"]
        elif dataset in {"report_rc", "fina_indicator", "dividend"}:
            suffix = []
        else:
            raise ValueError(f"不支持的 refresh dataset: {dataset}")

        for ts_code in stock_pool:
            file_name = "__".join(sanitize_cache_key_parts([ts_code, *suffix])) + ".csv"
            path = cache_root / dataset / file_name
            if path.exists():
                path.unlink()


def update_trade_cal_cache(
    pro,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
) -> tuple[pd.Timestamp, ...]:
    frame = update_incremental_cache(
        cache=cache,
        dataset="trade_cal",
        key_parts=["full", "is_open_1"],
        requested_start_date=start_date,
        requested_end_date=end_date,
        date_column="cal_date",
        fetcher=lambda fetch_start, fetch_end: pro.trade_cal(exchange="", start_date=fetch_start, end_date=fetch_end, is_open="1"),
        empty_columns=["cal_date", "is_open"],
        sort_columns=["cal_date"],
    )
    dates = pd.to_datetime(frame["cal_date"].astype(str), format="%Y%m%d", errors="coerce").dropna()
    if dates.empty:
        raise ValueError("交易日历为空。")
    return tuple(sorted(dates.tolist()))


def update_daily_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
    trading_dates: tuple[pd.Timestamp, ...],
) -> pd.DataFrame:
    effective_end_date = resolve_trade_date_on_or_before(trading_dates, end_date)
    if effective_end_date is None:
        return pd.DataFrame(columns=["ts_code", "trade_date", "close"])
    return update_incremental_cache(
        cache=cache,
        dataset="daily",
        key_parts=[ts_code, "close"],
        requested_start_date=start_date,
        requested_end_date=effective_end_date,
        date_column="trade_date",
        fetcher=lambda fetch_start, fetch_end: pro.daily(ts_code=ts_code, start_date=fetch_start, end_date=fetch_end, fields="ts_code,trade_date,close"),
        empty_columns=["ts_code", "trade_date", "close"],
        sort_columns=["trade_date"],
    )


def update_daily_basic_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
    trading_dates: tuple[pd.Timestamp, ...],
) -> pd.DataFrame:
    effective_end_date = resolve_trade_date_on_or_before(trading_dates, end_date)
    if effective_end_date is None:
        return pd.DataFrame(columns=["ts_code", "trade_date", "pe_ttm"])
    return update_incremental_cache(
        cache=cache,
        dataset="daily_basic",
        key_parts=[ts_code, "pe_ttm"],
        requested_start_date=start_date,
        requested_end_date=effective_end_date,
        date_column="trade_date",
        fetcher=lambda fetch_start, fetch_end: pro.daily_basic(ts_code=ts_code, start_date=fetch_start, end_date=fetch_end, fields="ts_code,trade_date,pe_ttm"),
        empty_columns=["ts_code", "trade_date", "pe_ttm"],
        sort_columns=["trade_date"],
    )


def update_report_rc_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    return update_incremental_cache(
        cache=cache,
        dataset="report_rc",
        key_parts=[ts_code],
        requested_start_date=start_date,
        requested_end_date=end_date,
        date_column="report_date",
        fetcher=lambda fetch_start, fetch_end: fetch_report_rc_from_tushare(pro, ts_code=ts_code, start_date=fetch_start, end_date=fetch_end),
        empty_columns=["report_date", "quarter", "org_name", "eps"],
        sort_columns=["report_date", "quarter", "org_name"],
    )


def update_fina_indicator_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    return update_incremental_cache(
        cache=cache,
        dataset="fina_indicator",
        key_parts=[ts_code],
        requested_start_date=start_date,
        requested_end_date=end_date,
        date_column="ann_date",
        fetcher=lambda fetch_start, fetch_end: pro.fina_indicator(ts_code=ts_code, start_date=fetch_start, end_date=fetch_end),
        empty_columns=["ann_date", "end_date", "eps"],
        sort_columns=["end_date", "ann_date"],
    )


def update_dividend_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    return update_incremental_cache(
        cache=cache,
        dataset="dividend",
        key_parts=[ts_code],
        requested_start_date=start_date,
        requested_end_date=end_date,
        date_column="ex_date",
        fetcher=lambda fetch_start, fetch_end: _fetch_dividend_frame(
            pro,
            ts_code=ts_code,
            start_date=fetch_start,
            end_date=fetch_end,
        ),
        empty_columns=["ts_code", "ex_date", "cash_div", "cash_div_tax", "div_proc"],
        sort_columns=["ex_date"],
    )


def _fetch_dividend_frame(
    pro,
    *,
    ts_code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if not hasattr(pro, "dividend"):
        return pd.DataFrame(columns=["ts_code", "ex_date", "cash_div", "cash_div_tax", "div_proc"])
    try:
        return pro.dividend(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except TypeError:
        return pro.dividend(ts_code=ts_code)


def resolve_trade_date_on_or_before(
    trading_dates: tuple[pd.Timestamp, ...],
    target_date: str,
) -> str | None:
    if not trading_dates:
        return None
    target = pd.Timestamp(target_date)
    valid = [date for date in trading_dates if date <= target]
    if not valid:
        return None
    return valid[-1].strftime("%Y%m%d")
