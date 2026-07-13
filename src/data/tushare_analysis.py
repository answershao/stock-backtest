from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.expected_return import GrowthInputs, calculate_expected_return_3y, resolve_target_quarter
from src.data.tushare_cache_helpers import read_single_cache_frame, read_stock_cache_frame
from src.data.tushare_expected_return import TushareConsensusSnapshot, build_consensus_growth_from_report_rc


@dataclass(frozen=True)
class ExpectedReturnTimeseriesRequest:
    ts_code: str
    start_date: str
    end_date: str
    cache_dir: str | Path
    pe_history_years: int = 10


def calculate_expected_return_from_cache(
    *,
    ts_code: str,
    as_of_date: str,
    cache_dir: str | Path,
    pe_history_years: int = 10,
) -> TushareConsensusSnapshot:
    cache_root = Path(cache_dir)
    trade_cal = read_single_cache_frame(cache_root, "trade_cal")
    effective_as_of_date = resolve_trade_date_on_or_before_from_cache(trade_cal, as_of_date)
    if effective_as_of_date is None:
        raise FileNotFoundError(f"缓存中找不到 {as_of_date} 之前的交易日: {cache_root / 'trade_cal'}")

    daily_basic = normalize_daily_basic(read_stock_cache_frame(cache_root, "daily_basic", ts_code))
    report_rc = normalize_report_rc(read_stock_cache_frame(cache_root, "report_rc", ts_code))
    fina_indicator = normalize_fina_indicator(read_stock_cache_frame(cache_root, "fina_indicator", ts_code))

    as_of_ts = pd.Timestamp(effective_as_of_date)
    daily_as_of = daily_basic[daily_basic["date"] <= as_of_ts]
    latest_row = daily_as_of.iloc[-1] if not daily_as_of.empty else None
    current_pe = None if latest_row is None else latest_row.get("pe_ttm")
    pe_window_start = as_of_ts - pd.DateOffset(years=pe_history_years)
    pe_history = daily_as_of.loc[daily_as_of["date"] >= pe_window_start, "pe_ttm"].dropna().tolist()

    base_quarter, base_ann_date, base_eps = resolve_base_annual_eps_with_ann_date(fina_indicator, as_of_ts)
    target_quarter = resolve_target_quarter(base_quarter)
    report_as_of = report_rc[report_rc["report_date"] <= as_of_ts].copy()
    end_eps, consensus_cagr_3y, org_count = build_consensus_growth_from_report_rc(
        report_as_of,
        target_quarter=target_quarter,
        base_eps=base_eps,
    )
    result = calculate_expected_return_3y(
        current_pe=current_pe,
        pe_history=pe_history,
        growth=GrowthInputs(future_3y_consensus_cagr=consensus_cagr_3y),
    )
    return TushareConsensusSnapshot(
        ts_code=ts_code,
        requested_as_of_date=as_of_date,
        as_of_date=effective_as_of_date.strftime("%Y%m%d"),
        current_pe=current_pe,
        target_pe_sample_size=len(pe_history),
        base_quarter=base_quarter,
        base_ann_date=base_ann_date,
        target_quarter=target_quarter,
        consensus_eps_base=base_eps,
        consensus_eps_target=end_eps,
        consensus_cagr_3y=consensus_cagr_3y,
        report_rows=len(report_as_of),
        report_orgs=org_count,
        result=result,
    )


def build_expected_return_timeseries(request: ExpectedReturnTimeseriesRequest) -> pd.DataFrame:
    cache_root = Path(request.cache_dir)
    trade_cal = read_single_cache_frame(cache_root, "trade_cal")
    trading_dates = pd.to_datetime(trade_cal["cal_date"].astype(str), format="%Y%m%d", errors="coerce").dropna().sort_values()
    start_ts = pd.Timestamp(request.start_date)
    end_ts = pd.Timestamp(request.end_date)
    trading_dates = trading_dates[(trading_dates >= start_ts) & (trading_dates <= end_ts)]
    if trading_dates.empty:
        raise ValueError(f"缓存中找不到 {request.start_date} 到 {request.end_date} 之间的交易日。")

    daily_basic = normalize_daily_basic(read_stock_cache_frame(cache_root, "daily_basic", request.ts_code))
    daily_close = read_stock_cache_frame(cache_root, "daily", request.ts_code).rename(columns={"trade_date": "date"}).copy()
    daily_close["date"] = pd.to_datetime(daily_close["date"], format="%Y%m%d", errors="coerce")
    daily_close["close"] = pd.to_numeric(daily_close["close"], errors="coerce")
    daily_close = daily_close.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    report_rc = normalize_report_rc(read_stock_cache_frame(cache_root, "report_rc", request.ts_code))
    fina_indicator = normalize_fina_indicator(read_stock_cache_frame(cache_root, "fina_indicator", request.ts_code))

    records: list[dict[str, object]] = []
    for as_of_ts in trading_dates:
        daily_as_of = daily_basic[daily_basic["date"] <= as_of_ts]
        latest_row = daily_as_of.iloc[-1] if not daily_as_of.empty else None
        current_pe = None if latest_row is None else latest_row.get("pe_ttm")
        pe_window_start = as_of_ts - pd.DateOffset(years=request.pe_history_years)
        pe_history = daily_as_of.loc[daily_as_of["date"] >= pe_window_start, "pe_ttm"].dropna().tolist()

        base_quarter, _, base_eps = resolve_base_annual_eps_with_ann_date(fina_indicator, as_of_ts)
        target_quarter = resolve_target_quarter(base_quarter)
        report_as_of = report_rc[report_rc["report_date"] <= as_of_ts]
        _, consensus_cagr_3y, _ = build_consensus_growth_from_report_rc(
            report_as_of,
            target_quarter=target_quarter,
            base_eps=base_eps,
        )
        result = calculate_expected_return_3y(
            current_pe=current_pe,
            pe_history=pe_history,
            growth=GrowthInputs(future_3y_consensus_cagr=consensus_cagr_3y),
        )
        close_as_of = daily_close[daily_close["date"] <= as_of_ts]
        records.append(
            {
                "date": as_of_ts,
                "close": None if close_as_of.empty else float(close_as_of.iloc[-1]["close"]),
                "mean_reversion_return_3y": result.mean_reversion_return_3y,
                "consensus_cagr_3y": consensus_cagr_3y,
                "expected_return_3y": result.expected_return_3y,
                "valid": result.valid,
                "reason": result.reason,
            }
        )
    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def normalize_daily_basic(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.rename(columns={"trade_date": "date"}).copy()
    frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d", errors="coerce")
    frame["pe_ttm"] = pd.to_numeric(frame["pe_ttm"], errors="coerce")
    return frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def normalize_report_rc(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    frame["report_date"] = pd.to_datetime(frame["report_date"], format="%Y%m%d", errors="coerce")
    frame["eps"] = pd.to_numeric(frame["eps"], errors="coerce")
    return frame.dropna(subset=["report_date"]).sort_values(["quarter", "org_name", "report_date"]).reset_index(drop=True)


def normalize_fina_indicator(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    frame["ann_date"] = pd.to_datetime(frame["ann_date"], format="%Y%m%d", errors="coerce")
    frame["end_date"] = pd.to_datetime(frame["end_date"], format="%Y%m%d", errors="coerce")
    frame["eps"] = pd.to_numeric(frame["eps"], errors="coerce")
    return frame.dropna(subset=["ann_date", "end_date", "eps"]).sort_values(["end_date", "ann_date"]).reset_index(drop=True)


def resolve_base_annual_eps_with_ann_date(
    fina_indicator: pd.DataFrame,
    as_of: pd.Timestamp,
) -> tuple[str | None, str | None, float | None]:
    if fina_indicator.empty:
        return None, None, None
    data = fina_indicator[fina_indicator["ann_date"] <= as_of].copy()
    if data.empty:
        return None, None, None
    data = data[data["end_date"].dt.strftime("%m%d") == "1231"]
    if data.empty:
        return None, None, None
    latest = data.sort_values(["end_date", "ann_date"]).drop_duplicates(subset=["end_date"], keep="last").iloc[-1]
    base_quarter = f"{latest['end_date'].year}Q4"
    ann_date = latest["ann_date"].strftime("%Y%m%d")
    base_eps = float(latest["eps"])
    return base_quarter, ann_date, base_eps if base_eps > 0 else None


def resolve_trade_date_on_or_before_from_cache(trade_cal: pd.DataFrame, as_of_date: str) -> pd.Timestamp | None:
    dates = pd.to_datetime(trade_cal["cal_date"].astype(str), format="%Y%m%d", errors="coerce").dropna().sort_values()
    if dates.empty:
        return None
    target = pd.Timestamp(as_of_date)
    valid = dates[dates <= target]
    if valid.empty:
        return None
    return valid.iloc[-1]
