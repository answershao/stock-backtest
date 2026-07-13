from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.expected_return import GrowthInputs, calculate_expected_return_3y, resolve_target_quarter
from src.data.tushare_cache_helpers import read_single_cache_frame, read_stock_cache_frame
from src.data.tushare_expected_return import (
    TushareConsensusSnapshot,
    build_consensus_growth_from_report_rc,
    build_tushare_consensus_snapshot,
    normalize_fina_indicator_frame,
    resolve_base_annual_eps_with_ann_date,
)


@dataclass(frozen=True)
class ExpectedReturnTimeseriesRequest:
    ts_code: str
    start_date: str
    end_date: str
    cache_dir: str | Path
    pe_history_years: int = 10


@dataclass(frozen=True)
class CachedStockAnalysisFrames:
    daily_basic: pd.DataFrame
    report_rc: pd.DataFrame
    fina_indicator: pd.DataFrame
    daily_basic_dates: np.ndarray
    report_dates: np.ndarray
    fina_ann_dates: np.ndarray

    @classmethod
    def from_cache(cls, *, cache_root: Path, ts_code: str) -> "CachedStockAnalysisFrames":
        daily_basic = normalize_daily_basic(read_stock_cache_frame(cache_root, "daily_basic", ts_code))
        report_rc = normalize_report_rc(read_stock_cache_frame(cache_root, "report_rc", ts_code))
        fina_indicator = normalize_fina_indicator(read_stock_cache_frame(cache_root, "fina_indicator", ts_code))
        return cls(
            daily_basic=daily_basic,
            report_rc=report_rc,
            fina_indicator=fina_indicator,
            daily_basic_dates=daily_basic["date"].to_numpy(),
            report_dates=report_rc["report_date"].to_numpy(),
            fina_ann_dates=fina_indicator["ann_date"].to_numpy(),
        )

    def resolve_current_pe_and_history(
        self,
        *,
        as_of_ts: pd.Timestamp,
        pe_history_years: int,
    ) -> tuple[float | None, list[float]]:
        end_index = self._right_index(self.daily_basic_dates, as_of_ts)
        if end_index == 0:
            return None, []

        current_value = self.daily_basic.iloc[end_index - 1]["pe_ttm"]
        current_pe = None if pd.isna(current_value) else float(current_value)
        start_index = self._left_index(self.daily_basic_dates, as_of_ts - pd.DateOffset(years=pe_history_years))
        pe_history = self.daily_basic.iloc[start_index:end_index]["pe_ttm"].dropna().astype(float).tolist()
        return current_pe, pe_history

    def resolve_report_as_of(self, as_of_ts: pd.Timestamp) -> pd.DataFrame:
        end_index = self._right_index(self.report_dates, as_of_ts)
        return self.report_rc.iloc[:end_index]

    def resolve_base_annual_eps(self, as_of_ts: pd.Timestamp) -> tuple[str | None, str | None, float | None]:
        end_index = self._right_index(self.fina_ann_dates, as_of_ts)
        return resolve_base_annual_eps_with_ann_date(self.fina_indicator.iloc[:end_index], as_of_ts)

    def resolve_close(self, as_of_ts: pd.Timestamp) -> float | None:
        end_index = self._right_index(self.daily_basic_dates, as_of_ts)
        if end_index == 0:
            return None
        value = self.daily_basic.iloc[end_index - 1]["close"]
        return None if pd.isna(value) else float(value)

    @staticmethod
    def _left_index(values: np.ndarray, ts: pd.Timestamp) -> int:
        return int(values.searchsorted(ts.to_datetime64(), side="left"))

    @staticmethod
    def _right_index(values: np.ndarray, ts: pd.Timestamp) -> int:
        return int(values.searchsorted(ts.to_datetime64(), side="right"))


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

    analysis = CachedStockAnalysisFrames.from_cache(cache_root=cache_root, ts_code=ts_code)
    as_of_ts = pd.Timestamp(effective_as_of_date)
    current_pe, pe_history = analysis.resolve_current_pe_and_history(as_of_ts=as_of_ts, pe_history_years=pe_history_years)
    base_quarter, base_ann_date, base_eps = analysis.resolve_base_annual_eps(as_of_ts)
    report_as_of = analysis.resolve_report_as_of(as_of_ts)
    return build_tushare_consensus_snapshot(
        ts_code=ts_code,
        requested_as_of_date=as_of_date,
        as_of_date=effective_as_of_date.strftime("%Y%m%d"),
        current_pe=current_pe,
        pe_history=pe_history,
        report_df=report_as_of,
        base_quarter=base_quarter,
        base_ann_date=base_ann_date,
        base_eps=base_eps,
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

    analysis = CachedStockAnalysisFrames.from_cache(cache_root=cache_root, ts_code=request.ts_code)

    records: list[dict[str, object]] = []
    for as_of_ts in trading_dates:
        current_pe, pe_history = analysis.resolve_current_pe_and_history(
            as_of_ts=as_of_ts,
            pe_history_years=request.pe_history_years,
        )
        base_quarter, _, base_eps = analysis.resolve_base_annual_eps(as_of_ts)
        target_quarter = resolve_target_quarter(base_quarter)
        report_as_of = analysis.resolve_report_as_of(as_of_ts)
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
        records.append(
            {
                "date": as_of_ts,
                "close": analysis.resolve_close(as_of_ts),
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
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def normalize_report_rc(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    frame["report_date"] = pd.to_datetime(frame["report_date"], format="%Y%m%d", errors="coerce")
    frame["eps"] = pd.to_numeric(frame["eps"], errors="coerce")
    return frame.dropna(subset=["report_date"]).sort_values(["quarter", "org_name", "report_date"]).reset_index(drop=True)


def normalize_fina_indicator(data: pd.DataFrame) -> pd.DataFrame:
    return normalize_fina_indicator_frame(data)


def resolve_trade_date_on_or_before_from_cache(trade_cal: pd.DataFrame, as_of_date: str) -> pd.Timestamp | None:
    dates = pd.to_datetime(trade_cal["cal_date"].astype(str), format="%Y%m%d", errors="coerce").dropna().sort_values()
    if dates.empty:
        return None
    target = pd.Timestamp(as_of_date)
    valid = dates[dates <= target]
    if valid.empty:
        return None
    return valid.iloc[-1]
