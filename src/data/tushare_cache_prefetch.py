from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.data.cache import TushareDataCache
from src.data.report_rc import normalize_report_rc_frame
from src.data.tushare_cache import sanitize_cache_key_parts
from src.data.tushare_cache_helpers import (
    filter_frame_by_date_range,
    merge_cache_frames,
    merge_cache_frames_with_dedupe,
    normalize_yyyymmdd_column,
    read_cache_frame,
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
    frame = cache.load_or_fetch(
        dataset="trade_cal",
        key_parts=[start_date, end_date, "is_open_1"],
        fetcher=lambda: pro.trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1"),
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
    now: pd.Timestamp | None = None,
    market_data_cutoff_time: str = "18:00",
    report_rc_start_date: str = FULL_HISTORY_START_DATE,
    refresh_datasets: tuple[str, ...] = (),
) -> TushareCacheArtifacts:
    current_time = pd.Timestamp.now() if now is None else pd.Timestamp(now)
    calendar_end_date = end_date or current_time.strftime("%Y%m%d")
    cache_root = Path(cache_dir)
    cache = TushareDataCache(cache_root, cache_only=False)
    clear_selected_cache_files(cache_root, stock_pool=stock_pool, datasets=refresh_datasets)
    trading_dates = update_trade_cal_cache(
        pro,
        cache=cache,
        start_date=FULL_HISTORY_START_DATE,
        end_date=calendar_end_date,
    )
    market_data_end_date = (
        resolve_latest_available_market_data_date(
            trading_dates,
            current_time,
            cutoff_time=market_data_cutoff_time,
        )
        if end_date is None
        else calendar_end_date
    )
    for ts_code in stock_pool:
        update_daily_basic_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=market_data_end_date, trading_dates=trading_dates)
        update_report_rc_cache(pro, ts_code, cache=cache, start_date=report_rc_start_date, end_date=calendar_end_date)
        update_fina_indicator_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=calendar_end_date)
        update_dividend_cache(pro, ts_code, cache=cache, start_date=FULL_HISTORY_START_DATE, end_date=calendar_end_date)
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

        if dataset == "daily_basic":
            suffix = ["pe_ttm", "close"]
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
        return pd.DataFrame(columns=["ts_code", "trade_date", "pe_ttm", "close"])
    return update_incremental_cache(
        cache=cache,
        dataset="daily_basic",
        key_parts=[ts_code, "pe_ttm", "close"],
        requested_start_date=start_date,
        requested_end_date=effective_end_date,
        date_column="trade_date",
        fetcher=lambda fetch_start, fetch_end: pro.daily_basic(
            ts_code=ts_code,
            start_date=fetch_start,
            end_date=fetch_end,
            fields="ts_code,trade_date,pe_ttm,close",
        ),
        empty_columns=["ts_code", "trade_date", "pe_ttm", "close"],
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
    frame = update_incremental_cache(
        cache=cache,
        dataset="report_rc",
        key_parts=[ts_code],
        requested_start_date=start_date,
        requested_end_date=end_date,
        date_column="report_date",
        fetcher=lambda fetch_start, fetch_end: fetch_report_rc_from_tushare(pro, ts_code=ts_code, start_date=fetch_start, end_date=fetch_end),
        empty_columns=["report_date", "report_title", "quarter", "org_name", "eps"],
        sort_columns=["report_date", "report_title", "quarter", "org_name"],
    )
    normalized = normalize_report_rc_frame(frame)
    if "report_id" in normalized.columns:
        normalized = normalized.drop(columns=["report_id"])
    if "report_date" in normalized.columns:
        normalized = normalized.copy()
        normalized["report_date"] = normalized["report_date"].dt.strftime("%Y%m%d")
    cache.write(dataset="report_rc", key_parts=[ts_code], frame=normalized)
    return normalized


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
        fetcher=lambda fetch_start, fetch_end: filter_annual_fina_indicator_frame(
            pro.fina_indicator(ts_code=ts_code, start_date=fetch_start, end_date=fetch_end)
        ),
        empty_columns=["ann_date", "end_date", "eps"],
        sort_columns=["end_date", "ann_date"],
        dedupe_subset=["end_date"],
        normalize_date_columns=["end_date"],
    )


def filter_annual_fina_indicator_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["ann_date", "end_date", "eps"])
    if "end_date" not in frame.columns:
        return frame.copy()
    annual_mask = frame["end_date"].astype(str).str.endswith("1231")
    return frame.loc[annual_mask].reset_index(drop=True)


def update_dividend_cache(
    pro,
    ts_code: str,
    *,
    cache: TushareDataCache,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    existing = read_cache_frame(cache.root_dir, dataset="dividend", key_parts=[ts_code])
    fetched = filter_implemented_dividend_frame(_fetch_dividend_frame(pro, ts_code=ts_code))
    if fetched is None:
        fetched = pd.DataFrame(
            columns=[
                "ts_code",
                "ann_date",
                "record_date",
                "ex_date",
                "imp_ann_date",
                "cash_div",
                "cash_div_tax",
                "stk_div",
                "stk_bo_rate",
                "stk_co_rate",
                "div_proc",
            ]
        )
    elif fetched.empty:
        fetched = pd.DataFrame(
            columns=list(fetched.columns)
            or [
                "ts_code",
                "ann_date",
                "record_date",
                "ex_date",
                "imp_ann_date",
                "cash_div",
                "cash_div_tax",
                "stk_div",
                "stk_bo_rate",
                "stk_co_rate",
                "div_proc",
            ]
        )

    for column in ["ann_date", "record_date", "ex_date", "imp_ann_date"]:
        existing = normalize_yyyymmdd_column(existing, column)
        fetched = normalize_yyyymmdd_column(fetched, column)
    combined = merge_cache_frames_with_dedupe(
        existing,
        fetched,
        sort_columns=_resolve_dividend_sort_columns(existing, fetched),
        dedupe_subset=["ex_date"],
    )
    cache.write(dataset="dividend", key_parts=[ts_code], frame=combined)
    return combined


def _fetch_dividend_frame(
    pro,
    *,
    ts_code: str,
) -> pd.DataFrame:
    return pro.dividend(
        ts_code=ts_code,
        fields="ts_code,ann_date,record_date,ex_date,imp_ann_date,cash_div,cash_div_tax,stk_div,stk_bo_rate,stk_co_rate,div_proc",
    )


def filter_implemented_dividend_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(
            columns=[
                "ts_code",
                "ann_date",
                "record_date",
                "ex_date",
                "imp_ann_date",
                "cash_div",
                "cash_div_tax",
                "stk_div",
                "stk_bo_rate",
                "stk_co_rate",
                "div_proc",
            ]
        )
    if "div_proc" not in frame.columns:
        return frame.copy()
    return frame.loc[frame["div_proc"].astype(str) == "实施"].reset_index(drop=True)


def _resolve_dividend_sort_columns(existing: pd.DataFrame, fetched: pd.DataFrame) -> list[str]:
    available_columns = set(existing.columns) | set(fetched.columns)
    sort_columns = [column for column in ["ex_date", "record_date", "ann_date", "imp_ann_date"] if column in available_columns]
    return sort_columns or ["ts_code"]


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


def resolve_latest_available_market_data_date(
    trading_dates: tuple[pd.Timestamp, ...],
    now: pd.Timestamp,
    *,
    cutoff_time: str = "18:00",
) -> str | None:
    if not trading_dates:
        return None

    current_time = pd.Timestamp(now)
    today = current_time.normalize()
    cutoff_hour, cutoff_minute = _parse_cutoff_time(cutoff_time)
    cutoff_today = today + pd.Timedelta(hours=cutoff_hour, minutes=cutoff_minute)
    if current_time < cutoff_today:
        target_date = today - pd.Timedelta(days=1)
    else:
        target_date = today
    return resolve_trade_date_on_or_before(trading_dates, target_date.strftime("%Y%m%d"))


def _parse_cutoff_time(raw: str) -> tuple[int, int]:
    value = str(raw).strip()
    try:
        hour_str, minute_str = value.split(":", maxsplit=1)
        hour = int(hour_str)
        minute = int(minute_str)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"非法行情截止时间: {raw}，格式应为 HH:MM") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"非法行情截止时间: {raw}，格式应为 HH:MM")
    return hour, minute
