"""
调仓日因子快照组装
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_backtest.core import config as cfg
from stock_backtest.factors.factor_primitives import (
    build_valuation_metrics,
    calc_peg,
    calc_score,
    pick_growth_value,
)


def build_single_factor_row(hist, as_of, code):
    latest = hist.iloc[-1]
    valuation = build_valuation_metrics(hist, as_of)
    growth = pick_growth_value(latest)
    roe = latest.get("roe")
    roe = float(roe) if pd.notna(roe) else np.nan
    peg = calc_peg(latest.get("pe_ttm"), growth)
    score = calc_score(growth, peg, valuation["pe_percentile"], roe)
    is_st = bool(latest.get("is_st", False)) if "is_st" in latest else False

    return {
        "date": as_of,
        "code": code,
        "industry": latest.get("industry", cfg.UNIVERSE.stock_industry_map.get(code, "")),
        "pe_ttm": latest.get("pe_ttm"),
        "pb": latest.get("pb"),
        "roe": roe,
        "g": growth,
        "peg": peg,
        "pe_mean": valuation["pe_mean"],
        "pe_p80": valuation["pe_p80"],
        "pe_p95": valuation["pe_p95"],
        "pe_percentile": valuation["pe_percentile"],
        "score": score,
        "listing_date": latest.get("listing_date"),
        "is_st": is_st,
        "valuation_obs": valuation["valuation_obs"],
    }


def build_factor_snapshot_frame(fundamentals, as_of, candidate_codes):
    if fundamentals.empty:
        raise ValueError("fundamentals 为空，无法生成研究版因子。")

    records = []
    for code in candidate_codes:
        hist = fundamentals[(fundamentals["code"] == code) & (fundamentals["date"] <= as_of)].copy()
        if hist.empty:
            continue
        hist = hist.sort_values("date")
        records.append(build_single_factor_row(hist, as_of, code))

    return pd.DataFrame(records).sort_values(["industry", "code"]).reset_index(drop=True)
