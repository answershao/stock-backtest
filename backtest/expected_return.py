from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median
from typing import Iterable

import pandas as pd


MAX_GROWTH_RATE = 0.35


@dataclass(frozen=True)
class GrowthInputs:
    future_3y_consensus_cagr: float | None = None
    profit_cagr_3y: float | None = None
    profit_cagr_2y: float | None = None
    profit_growth_1y: float | None = None


@dataclass(frozen=True)
class ExpectedReturnInput:
    current_pe: float | None
    pe_history: Iterable[float | int | None]
    growth: GrowthInputs


@dataclass(frozen=True)
class ExpectedReturnResult:
    expected_return_3y: float | None
    mean_reversion_return_3y: float | None
    current_pe: float | None
    target_pe: float | None
    g: float | None
    growth_source: str | None
    valid: bool
    reason: str | None = None


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


class ExpectedReturn3YCalculator:
    """Calculator for the design.md section 4 expected annualized return."""

    def __init__(
        self,
        *,
        winsorize_lower_quantile: float = 0.05,
        winsorize_upper_quantile: float = 0.95,
        min_positive_pe_samples: int = 12,
    ) -> None:
        self.winsorize_lower_quantile = winsorize_lower_quantile
        self.winsorize_upper_quantile = winsorize_upper_quantile
        self.min_positive_pe_samples = min_positive_pe_samples

    def calculate(self, data: ExpectedReturnInput) -> ExpectedReturnResult:
        current_pe = data.current_pe
        if current_pe is None:
            return self._invalid(current_pe, None, None, None, "current_pe_missing")
        if current_pe <= 0:
            return self._invalid(current_pe, None, None, None, "current_pe_non_positive")

        target_pe = self.resolve_target_pe(data.pe_history)
        if target_pe is None:
            return self._invalid(current_pe, None, None, None, "target_pe_missing")

        growth = self.resolve_growth_rate(data.growth)
        if growth is None:
            return self._invalid(current_pe, target_pe, None, None, "g_missing")

        g, growth_source = growth
        try:
            mean_reversion_return_3y = (target_pe / current_pe) ** (1 / 3) - 1
            expected_return_3y = ((target_pe / current_pe) ** (1 / 3)) * (1 + g) - 1
        except (TypeError, ValueError, ZeroDivisionError):
            return self._invalid(current_pe, target_pe, g, growth_source, "expected_return_uncomputable")

        return ExpectedReturnResult(
            expected_return_3y=expected_return_3y,
            mean_reversion_return_3y=mean_reversion_return_3y,
            current_pe=current_pe,
            target_pe=target_pe,
            g=g,
            growth_source=growth_source,
            valid=True,
        )

    def resolve_target_pe(self, pe_history: Iterable[float | int | None]) -> float | None:
        values = [float(value) for value in pe_history if value is not None and value > 0]
        if len(values) < self.min_positive_pe_samples:
            return None

        robust_mean = self._winsorized_mean(values)
        if robust_mean is not None:
            return robust_mean

        return median(values)

    def resolve_growth_rate(self, growth: GrowthInputs) -> tuple[float, str] | None:
        candidates = (
            ("future_3y_consensus_cagr", growth.future_3y_consensus_cagr),
            ("profit_cagr_3y", growth.profit_cagr_3y),
            ("profit_cagr_2y", growth.profit_cagr_2y),
            ("profit_growth_1y", growth.profit_growth_1y),
        )

        for source, value in candidates:
            if value is None:
                continue
            if value <= -1:
                return None
            return min(float(value), MAX_GROWTH_RATE), source

        return None

    def _winsorized_mean(self, values: list[float]) -> float | None:
        if not values:
            return None

        ordered = sorted(values)
        lower = self._quantile(ordered, self.winsorize_lower_quantile)
        upper = self._quantile(ordered, self.winsorize_upper_quantile)
        cleaned = [min(max(value, lower), upper) for value in ordered]
        if not cleaned:
            return None
        return mean(cleaned)

    @staticmethod
    def _quantile(values: list[float], q: float) -> float:
        if q <= 0:
            return values[0]
        if q >= 1:
            return values[-1]

        position = (len(values) - 1) * q
        lower_index = int(position)
        upper_index = min(lower_index + 1, len(values) - 1)
        weight = position - lower_index

        lower = values[lower_index]
        upper = values[upper_index]
        return lower + (upper - lower) * weight

    @staticmethod
    def _invalid(
        current_pe: float | None,
        target_pe: float | None,
        g: float | None,
        growth_source: str | None,
        reason: str,
    ) -> ExpectedReturnResult:
        return ExpectedReturnResult(
            expected_return_3y=None,
            mean_reversion_return_3y=None,
            current_pe=current_pe,
            target_pe=target_pe,
            g=g,
            growth_source=growth_source,
            valid=False,
            reason=reason,
        )


def calculate_expected_return_3y(
    current_pe: float | None,
    pe_history: Iterable[float | int | None],
    growth: GrowthInputs,
    *,
    calculator: ExpectedReturn3YCalculator | None = None,
) -> ExpectedReturnResult:
    engine = calculator or ExpectedReturn3YCalculator()
    return engine.calculate(
        ExpectedReturnInput(
            current_pe=current_pe,
            pe_history=pe_history,
            growth=growth,
        )
    )


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
    df = pro.report_rc(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.copy()


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


def resolve_target_quarter(base_quarter: str | None) -> str | None:
    if not base_quarter or not base_quarter.endswith("Q4"):
        return None
    year = int(base_quarter[:4])
    return f"{year + 3}Q4"


def build_consensus_growth_from_report_rc(
    report_df: pd.DataFrame,
    *,
    target_quarter: str | None,
    base_eps: float | None,
) -> tuple[float | None, float | None, int]:
    if report_df is None or report_df.empty:
        return None, None, 0
    if target_quarter is None or base_eps is None or base_eps <= 0:
        return None, None, 0

    data = report_df.copy()
    data = data[data["quarter"] == target_quarter]
    data["eps"] = pd.to_numeric(data["eps"], errors="coerce")
    data = data[data["eps"].notna()]
    if data.empty:
        return None, None, 0

    data["report_date"] = pd.to_datetime(data["report_date"], format="%Y%m%d", errors="coerce")
    data = data.dropna(subset=["report_date", "org_name", "quarter"]).sort_values(["org_name", "quarter", "report_date"])
    latest_per_org_quarter = data.groupby(["org_name", "quarter"], as_index=False).tail(1)
    org_count = int(latest_per_org_quarter["org_name"].nunique())

    consensus = latest_per_org_quarter.groupby("quarter", as_index=False)["eps"].mean()
    consensus_map = {str(row["quarter"]): float(row["eps"]) for _, row in consensus.iterrows()}

    end_eps = consensus_map.get(target_quarter)
    if end_eps is None or end_eps <= 0:
        return None, None, org_count

    cagr = (end_eps / base_eps) ** (1 / 3) - 1
    return end_eps, cagr, org_count


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


def expected_return_demo_600519_20150630(
    token: str,
    http_url: str = "https://tu.brze.top",
) -> TushareConsensusSnapshot:
    pro = create_tushare_pro(token=token, http_url=http_url)
    return calculate_expected_return_3y_from_tushare(
        pro,
        request=TushareExpectedReturnRequest(
            ts_code="600519.SH",
            as_of_date="20150630",
        ),
    )
