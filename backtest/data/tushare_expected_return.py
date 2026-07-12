from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from backtest.expected_return import (
    ExpectedReturn3YCalculator,
    ExpectedReturnResult,
    GrowthInputs,
    build_consensus_growth_from_report_rc,
    calculate_expected_return_3y,
    resolve_target_quarter,
)


@dataclass(frozen=True)
class TushareConsensusSnapshot:
    ts_code: str
    requested_as_of_date: str
    as_of_date: str
    current_pe: float | None
    target_pe_sample_size: int
    base_quarter: str | None
    base_ann_date: str | None
    target_quarter: str | None
    consensus_eps_base: float | None
    consensus_eps_target: float | None
    consensus_cagr_3y: float | None
    report_rows: int
    report_orgs: int
    result: ExpectedReturnResult


@dataclass(frozen=True)
class TushareExpectedReturnRequest:
    ts_code: str
    as_of_date: str
    pe_history_years: int = 10
    report_rc_start_date: str = "20100101"


def create_tushare_pro(token: str, http_url: str = "https://tu.brze.top"):
    import tushare as ts
    from tushare.pro import client as _ts_client

    _ts_client.DataApi._DataApi__http_url = http_url
    return ts.pro_api(token)


def years_before(date_str: str, years: int) -> str:
    dt = datetime.strptime(date_str, "%Y%m%d")
    return dt.replace(year=dt.year - years).strftime("%Y%m%d")


def fetch_current_pe_from_tushare(pro, ts_code: str, trade_date: str) -> float | None:
    df = pro.daily_basic(ts_code=ts_code, trade_date=trade_date, fields="ts_code,trade_date,pe_ttm")
    if df is None or df.empty:
        return None
    value = df.iloc[0].get("pe_ttm")
    return float(value) if pd.notna(value) else None


def resolve_trade_date_on_or_before(pro, trade_date: str) -> str | None:
    current = datetime.strptime(trade_date, "%Y%m%d")
    start = current.replace(year=current.year - 1).strftime("%Y%m%d")
    cal = pro.trade_cal(exchange="", start_date=start, end_date=trade_date, is_open="1")
    if cal is None or cal.empty:
        return None
    cal = cal.copy()
    cal["cal_date"] = cal["cal_date"].astype(str)
    dates = sorted(cal["cal_date"].tolist())
    if not dates:
        return None
    return dates[-1]


def fetch_pe_history_from_tushare(pro, ts_code: str, start_date: str, end_date: str) -> list[float]:
    df = pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date, fields="ts_code,trade_date,pe_ttm")
    if df is None or df.empty:
        return []
    series = pd.to_numeric(df["pe_ttm"], errors="coerce").dropna()
    return [float(value) for value in series.tolist() if value > 0]


def fetch_report_rc_from_tushare(pro, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    limit = 3000
    offset = 0

    while True:
        df = pro.report_rc(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        if df is None or df.empty:
            break

        frames.append(df.copy())
        if len(df) < limit:
            break
        offset += limit

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fetch_actual_annual_eps_from_tushare(pro, ts_code: str, as_of_date: str) -> tuple[str | None, str | None, float | None]:
    start_date = years_before(as_of_date, 5)
    df = pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=as_of_date)
    if df is None or df.empty:
        return None, None, None

    data = df.copy()
    data["ann_date"] = pd.to_datetime(data["ann_date"], format="%Y%m%d", errors="coerce")
    data["end_date"] = pd.to_datetime(data["end_date"], format="%Y%m%d", errors="coerce")
    data["eps"] = pd.to_numeric(data["eps"], errors="coerce")
    as_of_ts = pd.to_datetime(as_of_date, format="%Y%m%d", errors="coerce")
    data = data.dropna(subset=["ann_date", "end_date", "eps"])
    data = data[data["ann_date"] <= as_of_ts]
    data = data[data["end_date"].dt.strftime("%m%d") == "1231"]
    if data.empty:
        return None, None, None

    data = data.sort_values(["end_date", "ann_date"]).drop_duplicates(subset=["end_date"], keep="last")
    latest = data.iloc[-1]
    base_quarter = f"{latest['end_date'].year}Q4"
    ann_date = latest["ann_date"].strftime("%Y%m%d")
    base_eps = float(latest["eps"])
    return base_quarter, ann_date, base_eps


def calculate_expected_return_3y_from_tushare(
    pro,
    *,
    request: TushareExpectedReturnRequest,
    calculator: ExpectedReturn3YCalculator | None = None,
) -> TushareConsensusSnapshot:
    effective_as_of_date = resolve_trade_date_on_or_before(pro, request.as_of_date) or request.as_of_date
    current_pe = fetch_current_pe_from_tushare(pro, request.ts_code, effective_as_of_date)
    pe_history = fetch_pe_history_from_tushare(
        pro,
        request.ts_code,
        years_before(effective_as_of_date, request.pe_history_years),
        effective_as_of_date,
    )
    report_df = fetch_report_rc_from_tushare(
        pro,
        request.ts_code,
        request.report_rc_start_date,
        effective_as_of_date,
    )
    base_quarter, base_ann_date, base_eps = fetch_actual_annual_eps_from_tushare(
        pro,
        request.ts_code,
        effective_as_of_date,
    )
    target_quarter = resolve_target_quarter(base_quarter)
    end_eps, consensus_cagr_3y, org_count = build_consensus_growth_from_report_rc(
        report_df,
        target_quarter=target_quarter,
        base_eps=base_eps,
    )

    result = calculate_expected_return_3y(
        current_pe=current_pe,
        pe_history=pe_history,
        growth=GrowthInputs(future_3y_consensus_cagr=consensus_cagr_3y),
        calculator=calculator,
    )
    return TushareConsensusSnapshot(
        ts_code=request.ts_code,
        requested_as_of_date=request.as_of_date,
        as_of_date=effective_as_of_date,
        current_pe=current_pe,
        target_pe_sample_size=len(pe_history),
        base_quarter=base_quarter,
        base_ann_date=base_ann_date,
        target_quarter=target_quarter,
        consensus_eps_base=base_eps,
        consensus_eps_target=end_eps,
        consensus_cagr_3y=consensus_cagr_3y,
        report_rows=0 if report_df is None else len(report_df),
        report_orgs=org_count,
        result=result,
    )
