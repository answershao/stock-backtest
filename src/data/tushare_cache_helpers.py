from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.tushare_cache import TushareDataCache, sanitize_cache_key_parts


def read_cache_frame(
    cache_root: Path,
    *,
    dataset: str,
    key_parts: list[str],
) -> pd.DataFrame:
    dataset_dir = cache_root / dataset
    canonical_file = dataset_dir / ("__".join(sanitize_cache_key_parts(key_parts)) + ".csv")
    if canonical_file.exists():
        return pd.read_csv(canonical_file)
    return pd.DataFrame()


def merge_cache_frames(existing: pd.DataFrame, fetched: pd.DataFrame, *, sort_columns: list[str]) -> pd.DataFrame:
    return merge_cache_frames_with_dedupe(
        existing,
        fetched,
        sort_columns=sort_columns,
        dedupe_subset=None,
    )


def merge_cache_frames_with_dedupe(
    existing: pd.DataFrame,
    fetched: pd.DataFrame,
    *,
    sort_columns: list[str],
    dedupe_subset: list[str] | None,
) -> pd.DataFrame:
    if existing.empty:
        base = fetched.copy()
    elif fetched.empty:
        base = existing.copy()
    else:
        base = pd.concat([existing, fetched], ignore_index=True)
    if base.empty:
        return base
    base = base.drop_duplicates()
    base = base.sort_values(sort_columns).reset_index(drop=True)
    if dedupe_subset:
        subset = [column for column in dedupe_subset if column in base.columns]
        if subset:
            base = base.drop_duplicates(subset=subset, keep="last").reset_index(drop=True)
    return base


def filter_frame_by_date_range(frame: pd.DataFrame, column: str, start_date: str, end_date: str) -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return frame
    values = pd.to_datetime(frame[column].astype(str), format="%Y%m%d", errors="coerce")
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    mask = values.notna() & (values >= start_ts) & (values <= end_ts)
    return frame.loc[mask].reset_index(drop=True)


def max_yyyymmdd(frame: pd.DataFrame, column: str) -> str | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_datetime(frame[column].astype(str), format="%Y%m%d", errors="coerce").dropna()
    if values.empty:
        return None
    return values.max().strftime("%Y%m%d")


def next_calendar_date(date_str: str) -> str:
    return (pd.Timestamp(date_str) + pd.Timedelta(days=1)).strftime("%Y%m%d")


def normalize_yyyymmdd_column(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return frame
    normalized = frame.copy()
    values = pd.to_datetime(normalized[column].astype(str), format="%Y%m%d", errors="coerce")
    normalized[column] = values.dt.strftime("%Y%m%d")
    return normalized


def update_incremental_cache(
    *,
    cache: TushareDataCache,
    dataset: str,
    key_parts: list[str],
    requested_start_date: str,
    requested_end_date: str,
    date_column: str,
    fetcher,
    empty_columns: list[str],
    sort_columns: list[str],
    dedupe_subset: list[str] | None = None,
    normalize_date_columns: list[str] | None = None,
) -> pd.DataFrame:
    existing = read_cache_frame(
        cache.root_dir,
        dataset=dataset,
        key_parts=key_parts,
    )
    if existing.empty:
        fetch_start_date = requested_start_date
    else:
        last_date = max_yyyymmdd(existing, date_column)
        fetch_start_date = next_calendar_date(last_date) if last_date else requested_start_date

    if fetch_start_date > requested_end_date:
        return existing

    fetched = fetcher(fetch_start_date, requested_end_date)
    if fetched is None:
        fetched = pd.DataFrame(columns=empty_columns)
    elif fetched.empty:
        fetched = pd.DataFrame(columns=list(fetched.columns) or empty_columns)

    columns_to_normalize = [date_column, *(normalize_date_columns or [])]
    for column in dict.fromkeys(columns_to_normalize):
        existing = normalize_yyyymmdd_column(existing, column)
        fetched = normalize_yyyymmdd_column(fetched, column)
    combined = merge_cache_frames_with_dedupe(
        existing,
        fetched,
        sort_columns=sort_columns,
        dedupe_subset=dedupe_subset,
    )
    cache.write(dataset=dataset, key_parts=key_parts, frame=combined)
    return combined


def read_single_cache_frame(cache_root: Path, dataset: str) -> pd.DataFrame:
    frame = read_cache_frame(
        cache_root,
        dataset=dataset,
        key_parts=["full", "is_open_1"],
    )
    if frame.empty:
        raise FileNotFoundError(f"缓存缺失: {cache_root / dataset}")
    return frame


def read_stock_cache_frame(cache_root: Path, dataset: str, ts_code: str) -> pd.DataFrame:
    key_parts = [ts_code, "pe_ttm", "close"] if dataset == "daily_basic" else [ts_code]
    if dataset == "dividend":
        key_parts = [ts_code]
    frame = read_cache_frame(
        cache_root,
        dataset=dataset,
        key_parts=key_parts,
    )
    if frame.empty:
        safe_ts_code = sanitize_cache_key_parts([ts_code])[0]
        raise FileNotFoundError(f"缓存缺失: {(cache_root / dataset / (safe_ts_code + '__*.csv'))}")
    return frame
