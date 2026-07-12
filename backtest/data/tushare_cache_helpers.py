from __future__ import annotations

from pathlib import Path

import pandas as pd

from backtest.data.tushare_cache import TushareDataCache


def sanitize_cache_key_parts(key_parts: list[str]) -> list[str]:
    return [
        part.strip()
        .replace("/", "-")
        .replace("\\", "-")
        .replace(":", "-")
        .replace("*", "-")
        .replace("?", "-")
        .replace('"', "-")
        .replace("<", "-")
        .replace(">", "-")
        .replace("|", "-")
        or "empty"
        for part in key_parts
    ]


def legacy_cache_patterns(*, dataset: str, key_parts: list[str]) -> list[str]:
    if dataset == "trade_cal":
        return ["*__*__is_open_1.csv"]
    if dataset == "daily":
        return [f"{sanitize_cache_key_parts(key_parts[:1])[0]}__*__*__close.csv"]
    if dataset == "daily_basic":
        return [f"{sanitize_cache_key_parts(key_parts[:1])[0]}__*__*__pe_ttm.csv"]
    if dataset in {"report_rc", "fina_indicator", "dividend"}:
        return [f"{sanitize_cache_key_parts(key_parts[:1])[0]}__*.csv"]
    return []


def read_incremental_cache_frame(
    cache_root: Path,
    *,
    dataset: str,
    key_parts: list[str],
    legacy_glob_patterns: list[str],
) -> pd.DataFrame:
    dataset_dir = cache_root / dataset
    canonical_file = dataset_dir / ("__".join(sanitize_cache_key_parts(key_parts)) + ".csv")
    if canonical_file.exists():
        return pd.read_csv(canonical_file)

    frames: list[pd.DataFrame] = []
    for pattern in legacy_glob_patterns:
        for file_path in sorted(dataset_dir.glob(pattern)):
            frames.append(pd.read_csv(file_path))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_cached_dataset_frame(
    *,
    cache: TushareDataCache,
    dataset: str,
    canonical_key_parts: list[str],
    legacy_glob_patterns: list[str],
    fallback_fetcher,
) -> pd.DataFrame:
    frame = read_incremental_cache_frame(
        cache.root_dir,
        dataset=dataset,
        key_parts=canonical_key_parts,
        legacy_glob_patterns=legacy_glob_patterns,
    )
    if not frame.empty:
        return frame
    return fallback_fetcher()


def merge_cache_frames(existing: pd.DataFrame, fetched: pd.DataFrame, *, sort_columns: list[str]) -> pd.DataFrame:
    if existing.empty:
        base = fetched.copy()
    elif fetched.empty:
        base = existing.copy()
    else:
        base = pd.concat([existing, fetched], ignore_index=True)
    if base.empty:
        return base
    base = base.drop_duplicates()
    return base.sort_values(sort_columns).reset_index(drop=True)


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
) -> pd.DataFrame:
    existing = read_incremental_cache_frame(
        cache.root_dir,
        dataset=dataset,
        key_parts=key_parts,
        legacy_glob_patterns=legacy_cache_patterns(dataset=dataset, key_parts=key_parts),
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

    existing = normalize_yyyymmdd_column(existing, date_column)
    fetched = normalize_yyyymmdd_column(fetched, date_column)
    combined = merge_cache_frames(existing, fetched, sort_columns=sort_columns)
    cache.write(dataset=dataset, key_parts=key_parts, frame=combined)
    return combined


def read_single_cache_frame(cache_root: Path, dataset: str) -> pd.DataFrame:
    frame = read_incremental_cache_frame(
        cache_root,
        dataset=dataset,
        key_parts=["full", "is_open_1"],
        legacy_glob_patterns=legacy_cache_patterns(dataset=dataset, key_parts=["full", "is_open_1"]),
    )
    if frame.empty:
        raise FileNotFoundError(f"缓存缺失: {cache_root / dataset}")
    return frame


def read_stock_cache_frame(cache_root: Path, dataset: str, ts_code: str) -> pd.DataFrame:
    key_parts = [ts_code, "pe_ttm"] if dataset == "daily_basic" else [ts_code]
    if dataset == "daily":
        key_parts = [ts_code, "close"]
    if dataset == "dividend":
        key_parts = [ts_code]
    frame = read_incremental_cache_frame(
        cache_root,
        dataset=dataset,
        key_parts=key_parts,
        legacy_glob_patterns=legacy_cache_patterns(dataset=dataset, key_parts=key_parts),
    )
    if frame.empty:
        safe_ts_code = sanitize_cache_key_parts([ts_code])[0]
        raise FileNotFoundError(f"缓存缺失: {(cache_root / dataset / (safe_ts_code + '__*.csv'))}")
    return frame
