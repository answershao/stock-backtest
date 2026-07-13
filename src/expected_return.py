from __future__ import annotations

from dataclasses import dataclass
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
